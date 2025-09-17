class VisionModule:
    def __init__(self):
        pass

    def init(self, params):
        # 初始化摄像头/AI模型等
        pass

    def detect(self):
        # 获取一帧并处理，返回检测/跟踪结果
        # 如 {"action": "move_forward", "target": "xxx"}
        return {"action": "move_forward", "target": None}