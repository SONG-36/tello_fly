import asyncio
from src.middleware.module.state_monitor import StateMonitor
from src.middleware.module.event_bus import subscribe_state, subscribe_event, shutdown
from src.drivers.tello import tello_sdk as sdk

async def main():
    # 连接真机
    await sdk.connect("192.168.10.1", 8889)

    mon = StateMonitor(period_ms=1000, max_heartbeat_fail=3)
    await mon.start()

    async def consume_state():
        async for s in subscribe_state():
            print("STATE:", s)

    async def consume_event():
        async for e in subscribe_event():
            print("EVENT:", e)

    t1 = asyncio.create_task(consume_state())
    t2 = asyncio.create_task(consume_event())

    # 运行 5 秒
    await asyncio.sleep(5)

    # ---- 正确的收尾都放在 async 函数内 ----
    await mon.stop()
    await shutdown()
    await sdk.close()     # 释放 UDP transport，避免下个测试拿不到控制权

    # 等消费者自然退出
    for t in (t1, t2):
        if not t.done():
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

if __name__ == "__main__":
    asyncio.run(main())
