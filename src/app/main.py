# src/app/main.py
print(">>> main.py 启动！")
from modules.control import MissionController
print(">>> 成功import MissionController")

def main():
    print(">>> main() 正在执行")
    mission = MissionController()
    print(">>> MissionController 实例化成功")
    mission.start_mission('patrol', params={})
    print(">>> mission.start_mission 完成")
    mission.loop()

if __name__ == "__main__":
    main()
