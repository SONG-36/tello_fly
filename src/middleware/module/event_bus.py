"""
event_bus.py — 轻量级发布订阅总线（asyncio）
- 两条通道：state（状态流）、event（事件/告警流）
- 多订阅者广播（每个订阅者独立队列，避免彼此阻塞）
- 背压：每个订阅队列可配置 maxsize；满时最新消息覆盖或丢弃策略可选
- 支持优雅关闭：shutdown() 后发布终止哨兵，订阅端自然退出

对上契约（文档化）：
  async def publish_state(payload: dict) -> None
  async def publish_event(payload: dict) -> None
  async def subscribe_state(maxsize: int = 100) -> AsyncIterator[dict]
  async def subscribe_event(maxsize: int = 100) -> AsyncIterator[dict]
  async def shutdown() -> None

使用示例（自测）：
  async def _demo():
      async def consumer(name):
          async for s in subscribe_state():
              print(name, "STATE:", s)

      t = asyncio.create_task(consumer("C1"))
      await publish_state({"alt": 1.2, "battery": 98})
      await asyncio.sleep(0.1)
      await shutdown()
      await t
"""

from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List, Optional

logger = logging.getLogger("middleware.event_bus")
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter(
        fmt="ts=%(asctime)s module=middleware.event_bus level=%(levelname)s event=%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# 内部终止哨兵
_SENTINEL = object()


class _Broadcast:
    """
    多订阅者广播通道：
      - register()：返回一个每订阅者独有的 asyncio.Queue
      - publish()：把消息扇出到所有订阅队列（满队列策略可调）
      - close()：向所有订阅队列投递哨兵，令订阅端自然退出
    """
    def __init__(self, name: str, drop_policy: str = "drop_oldest") -> None:
        self._name = name
        self._subs: List[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._closed = False
        # 满队列策略：drop_oldest / drop_newest / block
        self._drop_policy = drop_policy

    async def register(self, maxsize: int = 100) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        async with self._lock:
            if self._closed:
                # 已关闭则直接塞一个哨兵，订阅端会立即结束
                await q.put(_SENTINEL)
            self._subs.append(q)
        logger.info(f"{self._name}_subscribe")
        return q

    async def unregister(self, q: asyncio.Queue) -> None:
        async with self._lock:
            try:
                self._subs.remove(q)
            except ValueError:
                pass

    async def publish(self, item: Dict) -> None:
        if self._closed:
            return
        # 扇出：逐个队列处理背压
        dead: List[asyncio.Queue] = []
        for q in list(self._subs):
            try:
                if q.full():
                    if self._drop_policy == "drop_oldest":
                        try:
                            _ = q.get_nowait()  # 丢弃一个旧的
                        except asyncio.QueueEmpty:
                            pass
                        q.put_nowait(item)
                    elif self._drop_policy == "drop_newest":
                        # 丢弃这条新消息：跳过
                        continue
                    else:  # block
                        await q.put(item)
                else:
                    q.put_nowait(item)
            except Exception as e:  # 不让单个订阅者影响总线
                logger.warning(f"{self._name}_publish_fail:{e}")
                dead.append(q)
        if dead:
            async with self._lock:
                for q in dead:
                    if q in self._subs:
                        self._subs.remove(q)

    async def close(self) -> None:
        self._closed = True
        for q in list(self._subs):
            try:
                q.put_nowait(_SENTINEL)
            except Exception:
                pass
        logger.info(f"{self._name}_closed")


# 两条总线：状态 / 事件
_state_bus = _Broadcast("state")
_event_bus = _Broadcast("event")


async def publish_state(payload: Dict) -> None:
    """
    发布状态：payload 示例
      {"alt": 0.8, "battery": 97, "lat": 32.99, "lon": 119.01}
    """
    await _state_bus.publish(payload)


async def publish_event(payload: Dict) -> None:
    """
    发布事件：payload 示例
      {"severity": 2, "name": "timeout", "json_ctx": {"task_id": "task-42"}}
    """
    await _event_bus.publish(payload)


async def shutdown() -> None:
    """优雅关闭：让所有订阅端自然退出。"""
    await _state_bus.close()
    await _event_bus.close()


async def _subscribe_generic(bus: _Broadcast, maxsize: int) -> AsyncIterator[Dict]:
    """
    通用订阅器：返回一个 async 迭代器，直到 shutdown() 被调用。
    使用：
      async for msg in subscribe_state():
          ...
    """
    q = await bus.register(maxsize=maxsize)
    try:
        while True:
            item = await q.get()
            if item is _SENTINEL:
                break
            yield item  # type: ignore[misc]
    finally:
        await bus.unregister(q)


# 对外订阅 API
def subscribe_state(maxsize: int = 100) -> AsyncIterator[Dict]:
    return _subscribe_generic(_state_bus, maxsize=maxsize)


def subscribe_event(maxsize: int = 100) -> AsyncIterator[Dict]:
    return _subscribe_generic(_event_bus, maxsize=maxsize)
