# src/drivers/tello_sdk.py

import socket
import threading

class TelloSDK:
    def __init__(self, tello_ip='192.168.10.1', tello_port=8889, local_port=9000):
        self.tello_address = (tello_ip, tello_port)
        self.local_address = ('', local_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(self.local_address)
        self.response = None
        self.receive_thread = threading.Thread(target=self._receive)
        self.receive_thread.daemon = True
        self.receive_thread.start()

        # 关键点：初始化时自动 handshake
        res = self.send_command("command")
        print(f">>> [TelloSDK] 连接无人机：发送 'command'，回应：{res}")

    def _receive(self):
        while True:
            try:
                self.response, _ = self.sock.recvfrom(1024)
            except Exception as e:
                print(f"[TelloSDK] Receive error: {e}")

    def send_command(self, command, timeout=5):
        self.response = None
        self.sock.sendto(command.encode('utf-8'), self.tello_address)
        for _ in range(timeout * 10):
            if self.response:
                return self.response.decode('utf-8')
            else:
                import time
                time.sleep(0.1)
        return "[TelloSDK] Timeout"

    def close(self):
        self.sock.close()

# 示例用法
if __name__ == "__main__":
    sdk = TelloSDK()
    print(sdk.send_command("command"))      # 进入SDK模式
    print(sdk.send_command("takeoff"))      # 起飞
    print(sdk.send_command("land"))         # 降落
    sdk.close()
