# ping_b.py
import socket, time
TELLO=("192.168.10.1",8889)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.bind(("",8889))        # 关键差异：强绑 8889
s.settimeout(3)
time.sleep(1)
for cmd in ["command","battery?"]:
    print("SEND:",cmd); s.sendto(cmd.encode(),TELLO)
    try:
        data,_=s.recvfrom(1024); print("RECV:",data.decode())
    except socket.timeout:
        print("RECV: <timeout>")
