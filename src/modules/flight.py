from drivers.tello_sdk import TelloSDK

class FlightModule:
    def __init__(self):
        self.sdk = TelloSDK()

    def init(self, params):
        # 初始化飞控，如解锁/检查/起飞前配置
        pass

    def execute_cmd(self, cmd):
        # 执行主控下发的动作
        # 比如 cmd="move_forward"
        if cmd == "move_forward":
            self.sdk.send_command("forward 20")
        # 其他指令分支
