import cv2
from src.drivers.tello.tello_sdk import TelloSDK
import time

def main():
    # 初始化并连接无人机，自动发送 streamon
    sdk = TelloSDK()
    res = sdk.send_command("streamon")
    print("发送 streamon 指令，回应：", res)
    time.sleep(2)  # 稍等无人机推流

    cap = cv2.VideoCapture("udp://@0.0.0.0:11111")
    if not cap.isOpened():
        print("无法连接到无人机流，请确保已收到 streamon 的 ok 回应！")
        return

    print("正在接收无人机视频流，按 q 退出...")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("未收到画面数据")
            continue
        cv2.imshow('Tello Camera Stream', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    sdk.close()

if __name__ == "__main__":
    main()
