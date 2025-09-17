from drivers.tello_sdk import TelloSDK

class FlightController:
    """飞行控制模块，封装无人机动作指令下发"""
    def __init__(self):
        self.sdk = TelloSDK()
        # 真正 handshake 放在这里
        res = self.sdk.send_command("command")
        print(f"[FlightController] 已连接无人机: {res}")

    def execute(self, action):
        """根据plan结果，下发无人机控制指令"""
        if action == "move_forward":
            self.sdk.send_command("forward 30")
        elif action == "search":
            self.sdk.send_command("cw 30")
        print(f"[FlightController] 执行动作: {action}")
