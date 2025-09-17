class Planner:
    """任务/轨迹/行为规划模块"""
    def __init__(self):
        print("[Planner] 规划模块初始化完成")

    def plan(self, obs):
        """根据感知结果，输出飞行动作计划（可用规则、状态机、后续AI）"""
        if obs.get("target_found", False):
            action = "move_forward"
        else:
            action = "search"
        print(f"[Planner] 输出动作计划: {action}")
        return action
