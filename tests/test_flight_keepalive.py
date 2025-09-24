# tests/test_flight_keepalive.py
import asyncio

IP, PORT = "192.168.10.1", 8889
LOCAL_PORT = 9031  # 换一个干净端口，避开之前绑定

class Proto(asyncio.DatagramProtocol):
    def __init__(self): self.q = asyncio.Queue(maxsize=32)
    def datagram_received(self, data, addr):
        msg = data.decode(errors="ignore").strip()
        print("RECV:", msg)
        try: self.q.put_nowait(msg)
        except asyncio.QueueFull: pass

async def drain(q: asyncio.Queue):
    try:
        while True: q.get_nowait()
    except asyncio.QueueEmpty:
        pass

async def send_and_wait(transport, proto, cmd, timeout=3.0, accept=None, drain_before=True):
    if drain_before:
        await drain(proto.q)
    print("SEND:", cmd)
    transport.sendto(cmd.encode(), (IP, PORT))
    if accept is None:
        accept = lambda s: bool(s)
    try:
        while True:
            resp = await asyncio.wait_for(proto.q.get(), timeout=timeout)
            if accept(resp):
                return resp
    except asyncio.TimeoutError:
        return "<timeout>"

async def main():
    loop = asyncio.get_running_loop()
    proto = Proto()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: proto, local_addr=("0.0.0.0", LOCAL_PORT)
    )

    ok_or_err = lambda s: s.lower() in {"ok", "error"}

    # 1) 强壮握手：最多尝试 3 次 command（每次间隔 0.6s）
    got = None
    for i in range(3):
        resp = await send_and_wait(transport, proto, "command", timeout=2.5, accept=ok_or_err)
        print(f"command[{i}] ->", resp)
        if resp.lower() == "ok":
            got = "ok"; break
        await asyncio.sleep(0.6)
    if got != "ok":
        print("未能进入SDK模式，建议：确认只剩这一个脚本在跑；必要时重启飞机。")
        transport.close(); return

    await asyncio.sleep(0.7)

    # 2) 启动心跳
    async def keepalive():
        while True:
            transport.sendto(b"battery?", (IP, PORT))
            await asyncio.sleep(1.0)
    ka = asyncio.create_task(keepalive())

    # 3) 起飞（即使超时也继续飞行流程，靠心跳避免10秒自降）
    resp = await send_and_wait(transport, proto, "takeoff", timeout=8.0, accept=ok_or_err)
    print("takeoff ->", resp)
    if resp == "<timeout>":
        print("提示：起飞ACK丢失常见；已用心跳保持飞行。")

    await asyncio.sleep(8)

    # 4) 降落
    resp = await send_and_wait(transport, proto, "land", timeout=8.0, accept=ok_or_err)
    print("land ->", resp)

    ka.cancel()
    try: await ka
    except asyncio.CancelledError: pass
    transport.close()

if __name__ == "__main__":
    asyncio.run(main())
