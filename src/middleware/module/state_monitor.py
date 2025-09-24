# state_monitor.py — 周期心跳与状态发布（M3）
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any

from src.drivers.tello import tello_sdk as driver
from . import event_bus

logger = logging.getLogger("middleware.state")
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter(
        fmt="ts=%(asctime)s module=middleware.state level=%(levelname)s event=%(message)s task_id=%(task_id)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


class StateMonitor:
    """
    周期性执行：
      1) 心跳（battery?）→ 0=OK, 非0=失败
      2) 发布状态（alt/battery/lat/lon 可扩展；先发布电量）
      3) 连续 N 次失败触发自愈重连，发布事件

    对外：
      - start()/stop() 控制后台任务
      - 可通过 event_bus.subscribe_state() 订阅状态
      - 事件通过 event_bus.subscribe_event() 订阅
    """

    def __init__(
        self,
        period_ms: int = 1000,
        max_heartbeat_fail: int = 3,
        publish_altitude: bool = False,  # 先留口位：如果后续有高度查询命令可开启
    ) -> None:
        self._period_ms = max(200, period_ms)  # 下限 200ms，避免过度频繁
        self._max_fail = max(1, max_heartbeat_fail)
        self._publish_altitude = publish_altitude

        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self._fail_count = 0

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop_evt.clear()
            self._task = asyncio.create_task(self._run(), name="StateMonitor")
            logger.info("state_monitor_started", extra={"task_id": "-"})

    async def stop(self) -> None:
        if self._task:
            self._stop_evt.set()
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("state_monitor_stopped", extra={"task_id": "-"})

    async def _run(self) -> None:
        period = self._period_ms / 1000.0
        while not self._stop_evt.is_set():
            # 1) 心跳（当前 driver.heartbeat 内部是 battery?）
            rc = await driver.heartbeat()
            if rc == 0:
                # 成功：失败计数清零
                self._fail_count = 0
                # 2) 发布状态（目前可从 heartbeat 的查询派生：电池电量；高度先占位为 0.0）
                #   - 如后续接入 'attitude?' 或其他查询，可在这里扩展并合并字段
                state: Dict[str, Any] = {
                    "alt": 0.0,       # 占位字段（单位 m，后续对接真实命令）
                    "battery": await self._battery_cached_or_dummy(),
                    "lat": None,      # 预留
                    "lon": None,      # 预留
                }
                await event_bus.publish_state(state)
            else:
                # 心跳失败
                self._fail_count += 1
                await self._emit_event(
                    name="heartbeat_fail",
                    severity=1,
                    ctx={"consecutive": self._fail_count},
                )
                # 连续失败达阈值 → 尝试自愈重连
                if self._fail_count >= self._max_fail:
                    await self._emit_event(name="reconnect_try", severity=2, ctx={})
                    rc2 = await driver.reconnect_if_needed()
                    if rc2 == 0:
                        self._fail_count = 0
                        await self._emit_event(name="reconnect_success", severity=0, ctx={})
                    else:
                        await self._emit_event(name="reconnect_fail", severity=3, ctx={})

            # 3) 周期等待（±10% 漂移窗口可后续加入抖动）
            try:
                await asyncio.wait_for(self._stop_evt.wait(), timeout=period)
            except asyncio.TimeoutError:
                pass  # 正常进入下一轮

    # ---- 工具与事件 ----

    async def _battery_cached_or_dummy(self) -> int:
        # 从驱动读取最近缓存；没有就给 -1 表示未知
        val = getattr(driver, "get_last_battery", lambda: None)()
        return val if isinstance(val, int) and val >= 0 else -1

    async def _emit_event(self, name: str, severity: int, ctx: Dict[str, Any]) -> None:
        payload = {"severity": severity, "name": name, "json_ctx": ctx}
        await event_bus.publish_event(payload)
