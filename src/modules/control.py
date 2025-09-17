from modules.vision import VisionModule
from modules.flight import FlightModule

class MissionController:
    def __init__(self):
        # 初始化各子模块
        self.vision = VisionModule()
        self.flight = FlightModule()
        self.state = 'INIT'
        self.running = False

    def start_mission(self, mission_type, params):
        print(f"[MissionController] Starting mission: {mission_type}")
        self.vision.init(params)    # 初始化视觉
        self.flight.init(params)    # 初始化飞控
        self.state = 'RUNNING'
        self.running = True
        # 状态反馈给上位机（如有）

    def loop(self):
        # 简化版主循环
        while self.running:
            # 任务执行
            vision_result = self.vision.detect()
            # ...可加异常处理/退出逻辑
            control_cmd = self.plan_action(vision_result)
            self.flight.execute_cmd(control_cmd)
            # 进度/状态上报（如有）
            # 检查任务完成/异常
            if self.check_end_condition():
                self.running = False
                self.end_mission('NORMAL')
        # 任务结束/异常处理
        print("[MissionController] Mission ended.")

    def plan_action(self, vision_result):
        # 根据视觉结果决定下一步动作
        # 例如追踪/规避/停飞等，返回控制命令
        return vision_result['action']

    def check_end_condition(self):
        # 判断是否任务完成或异常退出
        return False

    def end_mission(self, reason):
        # 任务结束/异常通知
        print(f"[MissionController] Mission ended with reason: {reason}")
