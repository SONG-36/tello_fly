# tests/smoke_tello_command.py
import asyncio

TelloIP, TelloPort = "192.168.10.1", 8889

class Proto(asyncio.DatagramProtocol):
    def __init__(self, fut): self.fut=fut
    def datagram_received(self, data, addr):
        if not self.fut.done():
            self.fut.set_result(data.decode().strip())

async def main():
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: Proto(fut), local_addr=("0.0.0.0", 9000)
    )
    transport.sendto(b"command", (TelloIP, TelloPort))
    try:
        resp = await asyncio.wait_for(fut, timeout=2.0)
        print("RECV:", resp)         # 期望: ok
    except asyncio.TimeoutError:
        print("RECV: <timeout>")     # 多半是Wi-Fi/防火墙/端口问题
    finally:
        transport.close()

if __name__ == "__main__":
    asyncio.run(main())
