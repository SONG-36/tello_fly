# tests/test_flight.py  — 带节奏与电量检查
import asyncio

IP, PORT = "192.168.10.1", 8889

class Proto(asyncio.DatagramProtocol):
    def __init__(self): self.q = asyncio.Queue()
    def datagram_received(self, data, addr):
        self.q.put_nowait(data.decode().strip())

async def send_wait(transport, proto, cmd, to=3.0):
    print("SEND:", cmd)
    transport.sendto(cmd.encode(), (IP, PORT))
    try:
        resp = await asyncio.wait_for(proto.q.get(), timeout=to)
    except asyncio.TimeoutError:
        resp = "<timeout>"
    print("RECV:", resp)
    return resp

async def main():
    loop = asyncio.get_running_loop()
    proto = Proto()
    transport, _ = await loop.create_datagram_endpoint(lambda: proto, local_addr=("0.0.0.0", 9000))

    # 进入 SDK
    await send_wait(transport, proto, "command")
    await asyncio.sleep(0.7)   # 关键：给点节奏

    # 电量检查
    bat = await send_wait(transport, proto, "battery?")
    try:
        batv = int(bat)
    except:
        batv = -1
    if batv >= 0:
        print("battery =", batv, "%")
        if batv < 15:
            print("电量过低，Tello 可能拒绝起飞。先充电。")
            transport.close(); return

    # 起飞
    await asyncio.sleep(0.5)
    take = await send_wait(transport, proto, "takeoff", to=5.0)
    if take.lower() != "ok":
        print("takeoff 被拒绝，可能是状态/姿态/环境问题。请重启飞机、确保平放/光线充足/仅此脚本在控制。")
        transport.close(); return

    # 悬停 5 秒
    await asyncio.sleep(5)

    # 降落
    await send_wait(transport, proto, "land", to=5.0)
    transport.close()

if __name__ == "__main__":
    asyncio.run(main())
