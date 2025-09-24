# tests/test_event_bus.py
import asyncio
from src.middleware.module import event_bus as bus

async def consumer(name: str):
    async for s in bus.subscribe_state(maxsize=2):
        print(name, "STATE:", s)

async def main():
    # 1) 启动订阅任务
    t = asyncio.create_task(consumer("C1"))
    # 关键：让调度器切换一次，让 consumer 真正跑到 `await q.get()`
    await asyncio.sleep(0)

    # 2) 发布两条状态
    await bus.publish_state({"alt": 1.2, "battery": 98})
    await asyncio.sleep(0.05)   # 给消费端时间处理（Windows 上尤其需要）
    await bus.publish_state({"alt": 1.3, "battery": 97})
    await asyncio.sleep(0.05)

    # 3) 优雅关闭
    await bus.shutdown()
    await t

if __name__ == "__main__":
    asyncio.run(main())
