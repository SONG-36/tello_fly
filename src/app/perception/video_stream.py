import cv2
import threading

class VideoStream:
    def __init__(self, url="udp://0.0.0.0:11111"):
        self.url = url
        self.cap = None
        self.running = False
        self.frame = None
        self.thread = None

    def start(self):
        if self.running:
            return
        self.cap = cv2.VideoCapture(self.url)
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame

    def get_frame(self):
        return self.frame

    def stop(self):
        self.running = False
        if self.cap:
            self.cap.release()
        self.frame = None
