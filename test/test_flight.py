from src.app.control.controller import FlightController

def test_flight():
    ctl = FlightController()
    ctl.sdk.send_command("command")   # 进入SDK模式
    ctl.sdk.send_command("takeoff")   # 起飞
    ctl.sdk.send_command("forward 30")# 前进30cm
    ctl.sdk.send_command("land")      # 降落
    ctl.sdk.close()

if __name__ == "__main__":
    test_flight()