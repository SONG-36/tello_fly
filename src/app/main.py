from app.perception.vision import VisionPerception
from app.planning.planner import Planner
from app.control.controller import FlightController

def main():
    print("[MainApp] 系统启动")
    vision = VisionPerception()
    planner = Planner()
    controller = FlightController()

    while True:
        obs = vision.detect()
        plan = planner.plan(obs)
        controller.execute(plan)

if __name__ == '__main__':
    main()
