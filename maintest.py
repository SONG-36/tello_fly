from djitellopy import Tello
import time

# 创建Tello对象
drone = Tello()
drone.connect()
print("电池电量:", drone.get_battery(), "%")

# 起飞
drone.takeoff()
print("起飞完成，悬停2秒...")

time.sleep(2)  # 悬停2秒

# 降落
drone.land()
print("降落完成")
