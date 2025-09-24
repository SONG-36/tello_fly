# src/middleware/module/cmd_queue.py
"""
CmdQueue — 串行命令下发队列
- 保障对 driver.send_cmd 的调用严格串行（SDK 友好）
- 不等待 ACK，只负责发送；ACK 由 driver 回调 → TaskScheduler 处理
- 队列满时（可选）阻塞等待；如需立即返回可改为 try_put

依赖：
  drivers.tello_sdk.send_cmd
使用：
  q = CmdQueue()
  await q.start()
  await q.push(CmdMsg(...))
"""

from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, Any

import src.drivers.tello.tello_sdk as driver

logger = logging.getLogger("middleware.cmd_queue")
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter(
        fmt="ts=%(asctime)s module=middleware.cmd_queue level=%(levelname)s event=%(message)s task_id=%(task_id)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)


@dataclass
class CmdMsg:
    task_id: str
    cmd: str
    json_param: Dict[str, Any] = field(default_factory=dict)
    timeout_ms: int = 2000


class CmdQueue:
    def __init__(self, maxsize: int = 128) -> None:
        self._q: asyncio.Queue[CmdMsg] = asyncio.Queue(maxsize=maxsize)
        self._worker: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._worker is None:
            self._worker = asyncio.create_task(self._worker_loop(), name="CmdQueueWorker")

    async def stop(self) -> None:
        self._stopped.set()
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None

    async def push(self, msg: CmdMsg) -> int:
        """入队（满则等待）。返回 0 表示受理。"""
        await self._q.put(msg)
        logger.info("enqueue", extra={"task_id": msg.task_id})
        return 0

    async def _worker_loop(self) -> None:
        """严格串行地把命令下发给驱动，不等待 ACK。"""
        while not self._stopped.is_set():
            msg: CmdMsg = await self._q.get()
            try:
                payload = {"task_id": msg.task_id, **(msg.json_param or {})}
                logger.info("send_cmd", extra={"task_id": msg.task_id})
                await driver.send_cmd(msg.cmd, payload, msg.timeout_ms)
            except Exception as e:
                logger.error(f"send_cmd_exception:{e}", extra={"task_id": msg.task_id})
            finally:
                self._q.task_done()
