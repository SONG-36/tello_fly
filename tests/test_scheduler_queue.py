import asyncio
from src.middleware.module.cmd_queue import CmdQueue, CmdMsg
from src.middleware.module.task_scheduler import TaskScheduler, OK
from src.middleware.module.event_bus import subscribe_event, shutdown
import src.drivers.tello.tello_sdk as sdk  # 真机或 mock 都可

async def main():
    # 连接（真机：确保已连 Tello Wi-Fi；mock 则忽略）
    try:
        await sdk.connect("192.168.10.1", 8889)
    except Exception:
        pass

    q = CmdQueue()
    await q.start()
    sched = TaskScheduler(q)

    # 事件监听（可选）
    async def ev():
        async for e in subscribe_event():
            print("EVENT:", e)
    tev = asyncio.create_task(ev())

    # 提交一个 takeoff 任务
    done = asyncio.get_running_loop().create_future()
    async def cb(task_id: str, status: int, detail):
        print("CALLBACK:", task_id, status, detail)
        done.set_result(status)

    msg = CmdMsg(task_id="task-001", cmd="takeoff", json_param={}, timeout_ms=8000)
    await sched.submit(msg, cb)
    status = await asyncio.wait_for(done, timeout=12.0)

    print("FINAL STATUS:", status == OK)

    await shutdown()
    await q.stop()
    tev.cancel()
    await sdk.close()

if __name__ == "__main__":
    asyncio.run(main())

