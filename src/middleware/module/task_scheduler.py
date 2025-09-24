# src/middleware/module/task_scheduler.py
"""
TaskScheduler — 任务管理（超时/重试/回调分发）
- submit(): 生成/登记在途 → 投递 CmdQueue → 等待 ACK
- 超时：默认 2000ms；重试 2 次、退避 200ms
- 回调：异步分发（不阻塞任意队列/driver 协程）
- 事件上报：成功/失败/超时通过 EventBus 发布

依赖：
  - CmdQueue（本模块旁边）
  - drivers.tello_sdk.set_resp_callback（接收 ACK）
  - middleware.module.event_bus.publish_event（事件上报）
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Callable, Awaitable, Any, Dict, Optional

import src.drivers.tello.tello_sdk as driver
from .cmd_queue import CmdQueue, CmdMsg
from . import event_bus

logger = logging.getLogger("middleware.scheduler")
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter(
        fmt="ts=%(asctime)s module=middleware.scheduler level=%(levelname)s event=%(message)s task_id=%(task_id)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# 极简错误码（与你项目里保持一致可替换为 common.errors）
OK = 0
ERR_TIMEOUT = 1201
ERR_GENERIC = 1500

TaskCallback = Callable[[str, int, Dict[str, Any] | None], Awaitable[None] | None]


@dataclass
class InFlight:
    future: asyncio.Future
    cb: Optional[TaskCallback]
    delivered: bool = False

class TaskScheduler:
    """调度器：对外提供 submit()；内部管理在途与 ACK 对应。"""

    def __init__(self, queue: CmdQueue, retry_max: int = 2, backoff_ms: int = 200,
                 grace_ms: int = 400,                     # ← 超时后的宽限窗口（ms）
                 assume_ok_cmds: tuple[str, ...] = ("takeoff", "land")):  # ← 这些命令超时也按成功
        self._queue = queue
        self._retry_max = retry_max
        self._backoff_ms = backoff_ms
        self._grace_ms = grace_ms
        self._assume_ok_cmds = tuple(c.lower() for c in assume_ok_cmds)
        self._inflight: dict[str, InFlight] = {}
        driver.set_resp_callback(self._on_driver_resp)

    # -------- 对外：提交任务 --------
    async def submit(self, msg: CmdMsg, cb: TaskCallback | None) -> None:
        """
        提交一个任务：内部会负责重试与回调。
        调用者无需等待；若想等待结果，可在 cb 里设置 Future。
        """
        asyncio.create_task(self._run_task(msg, cb), name=f"TaskRunner:{msg.task_id}")

    # -------- 驱动回调入口 --------
    def _on_driver_resp(self, cmd: str, ok: int, payload: Dict[str, Any] | None) -> None:  # noqa: ARG002
        task_id = "-"
        if payload and isinstance(payload, dict):
            task_id = str(payload.get("task_id", "-"))
        inf = self._inflight.get(task_id)
        if not inf:
            logger.warning("ack_unmatched", extra={"task_id": task_id})
            return

        # 1) 把结果写进 future（若还未完成）
        fut = inf.future
        if not fut.done():
            fut.set_result((ok, payload))

        # 2) 双保险：如果尚未对上层交付，则立即交付一次
        if not inf.delivered:
            inf.delivered = True
            status = OK if int(ok) == 1 else ERR_GENERIC
            asyncio.create_task(self._dispatch_cb(task_id, status, payload, inf.cb), name=f"TaskCallback:{task_id}")
            # 事件也一起发
            asyncio.create_task(
                self._emit_event(
                    name="ack_success" if status == OK else "ack_fail",
                    extra={"task_id": task_id, "payload": payload or {}},
                    severity=0 if status == OK else 2,
                ),
                name=f"TaskEvent:{task_id}",
            )
        logger.info("ack_received", extra={"task_id": task_id})

    # -------- 内部：执行一次任务（含重试） --------
    async def _run_task(self, base_msg: CmdMsg, cb: TaskCallback | None) -> None:
        attempts = self._retry_max + 1
        # 每次尝试都新建一个 Future，避免旧未来状态干扰
        for attempt in range(attempts):
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self._inflight[base_msg.task_id] = InFlight(future=fut, cb=cb)

            # 投递到串行队列
            await self._queue.push(base_msg)

            try:
                # 等待 ACK 或超时
                ok, payload = await asyncio.wait_for(
                    fut, timeout=base_msg.timeout_ms / 1000.0
                )
                # 收到 ACK，分发回调
                status = OK if int(ok) == 1 else ERR_GENERIC
                await self._dispatch_cb(base_msg.task_id, status, payload, cb)
                # 上报事件（成功/失败）
                await self._emit_event(
                    name="ack_success" if status == OK else "ack_fail",
                    extra={"task_id": base_msg.task_id, "payload": payload or {}},
                    severity=0 if status == OK else 2,
                )
                del self._inflight[base_msg.task_id]
                return
            except asyncio.TimeoutError:
                logger.error("timeout", extra={"task_id": base_msg.task_id})
                await self._emit_event(
                    name="timeout",
                    extra={"task_id": base_msg.task_id, "attempt": attempt},
                    severity=2,
                )

                inf = self._inflight.get(base_msg.task_id)

                # 宽限期内再等一次，接可能的迟到 ACK
                try:
                    ok, payload = await asyncio.wait_for(fut, timeout=self._grace_ms / 1000.0)
                    if inf and inf.delivered:
                        return  # 已由回调路径交付
                    status = OK if int(ok) == 1 else ERR_GENERIC
                    await self._dispatch_cb(base_msg.task_id, status, payload, inf.cb if inf else None)
                    await self._emit_event(
                        name="ack_success" if status == OK else "ack_fail",
                        extra={"task_id": base_msg.task_id, "payload": payload or {}},
                        severity=0 if status == OK else 2,
                    )
                    if inf:
                        inf.delivered = True
                    return
                except asyncio.TimeoutError:
                    pass
                finally:
                    # 不 cancel future，避免迟到 set_result 抛 CancelledError
                    self._inflight.pop(base_msg.task_id, None)

                # 仍然没有 ACK
                if base_msg.cmd.lower() in self._assume_ok_cmds:
                    await self._dispatch_cb(base_msg.task_id, OK, {"ack": True, "assumed": True}, cb)
                    await self._emit_event(name="ack_success_assumed", extra={"task_id": base_msg.task_id}, severity=1)
                    return

                if attempt < attempts - 1:
                    await asyncio.sleep(self._backoff_ms / 1000.0)
                    base_msg = replace(base_msg)
                    continue
                else:
                    await self._dispatch_cb(base_msg.task_id, ERR_TIMEOUT, {"error": "timeout"}, cb)
                    return

    async def _dispatch_cb(self, task_id: str, status: int, detail: Dict[str, Any] | None, cb: TaskCallback | None) -> None:
        """异步分发应用回调，避免阻塞任何内部协程。"""
        if cb is None:
            return
        async def _invoke():
            try:
                r = cb(task_id, status, detail)  # 允许 sync/async
                if asyncio.iscoroutine(r):
                    await r
            except Exception as e:
                logger.error(f"cb_exception:{e}", extra={"task_id": task_id})
        asyncio.create_task(_invoke(), name=f"TaskCallback:{task_id}")

    async def _emit_event(self, name: str, extra: Dict[str, Any], severity: int) -> None:
        payload = {"severity": severity, "name": name, "json_ctx": extra}
        await event_bus.publish_event(payload)
