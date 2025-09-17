import cv2

class CameraDriver:
    """摄像头驱动，负责图像采集"""
    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        print("[CameraDriver] 摄像头初始化完成")

    def get_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            print("[CameraDriver] 获取帧失败")
            return None
        return frame

    def release(self):
        self.cap.release()
