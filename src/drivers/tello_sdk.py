import socket
import threading
import signal
import atexit
import sys

class TelloSDK:
    def __init__(self, tello_ip='192.168.10.1', tello_port=8889, local_port=9000):
        self.tello_address = (tello_ip, tello_port)
        self.local_address = ('', local_port)
        self.response = None
        self._running = True

        # 端口占用检测
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 允许端口重用（可选，部分系统有效）
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(self.local_address)
        except OSError as e:
            print(f"[TelloSDK][错误] 本地端口 {local_port} 已被占用/未释放！\n"
                  f"请确认没有其他进程正在运行无人机程序，或等待系统释放端口后再试。\n"
                  f"详细: {e}")
            self.sock.close()
            raise

        self.receive_thread = threading.Thread(target=self._receive)
        self.receive_thread.daemon = True
        self.receive_thread.start()

        # 注册退出清理
        atexit.register(self.close)

        res = self.send_command("command")
        print(f">>> [TelloSDK] 连接无人机：发送 'command'，回应：{res}")

    def _receive(self):
        while self._running:
            try:
                self.response, _ = self.sock.recvfrom(1024)
            except OSError:
                # socket关闭时正常退出
                break
            except Exception as e:
                print(f"[TelloSDK] Receive error: {e}")
                break

    def send_command(self, command, timeout=5):
        self.response = None
        self.sock.sendto(command.encode('utf-8'), self.tello_address)
        import time
        for _ in range(timeout * 10):
            if self.response:
                return self.response.decode('utf-8')
            time.sleep(0.1)
        return "[TelloSDK] Timeout"

    def _cleanup(self, signum=None, frame=None):
        print("[TelloSDK] 检测到退出信号，正在优雅关闭...")
        self.close()
        sys.exit(0)   # 立即退出程序（防止多余的残余进程）

    def close(self):
        self._running = False
        try:
            self.sock.close()
        except Exception:
            pass
        if hasattr(self, 'receive_thread') and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1)
        print("[TelloSDK] 已释放socket和线程资源。")

