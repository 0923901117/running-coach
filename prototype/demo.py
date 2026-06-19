import sys; sys.path.insert(0, "prototype")
from engine import init_state, update, state_to_dict

def show(s, title):
    d = state_to_dict(s)
    sep = "=" * 50
    print(f"\n{sep}")
    print(f"  {title}")
    print(f"  Phase: {d['phase']}")
    if d["runner"]["goal"] != "0周0.0km":
        rr = d["runner"]
        print(f"  跑者: 年龄{rr['age']} 体重{rr['weight']} 水平{rr['fitness_level']}")
        print(f"  目标: {rr['goal']}")
    p = d["progress"]
    if p["total_sessions"] > 0:
        print(f"  进度: {p['completed_sessions']}/{p['total_sessions']} ({p['completion_pct']}%)")
        print(f"  周{p['current_week']}/天{p['current_day']} 未达标:{p['consecutive_under']} 超额:{p['consecutive_over']}")
    if d["injury_alerts"]:
        a = d["injury_alerts"][-1]
        print(f"  伤病: [{a['level']}] {a['diagnosis']}")
    print("  消息:")
    for m in d["messages"][-3:]:
        print(f"    {m}")

# 场景1: 完整摸底
s = init_state()
s = update(s, {"type": "START_ASSESSMENT"})
show(s, "场景1.1: 开始摸底")

s = update(s, {"type": "SET_GOAL", "distance_km": 5.0, "deadline_weeks": 8})
show(s, "场景1.2: 设定目标 8周5公里")

s = update(s, {"type": "SET_FITNESS", "level": "zero", "available_days": 3})
show(s, "场景1.3: 设定体能 零基础/每周3天")

s = update(s, {"type": "SET_BODY_INFO", "age": 28, "weight": 70})
show(s, "场景1.4: 身体信息 28岁/70kg")

s = update(s, {"type": "GENERATE_PLAN"})
show(s, "场景1.5: 生成8周训练计划")

# 场景2: 打卡确认
s = update(s, {"type": "CHECK_IN", "distance_km": 2.0, "pace": "800", "feel": "有点喘但还行"})
show(s, "场景2: 打卡待确认")

s = update(s, {"type": "CONFIRM_CHECK_IN"})
show(s, "场景2续: 确认打卡完成")

# 场景3: 伤病
s = update(s, {"type": "REPORT_INJURY", "symptom": "膝盖外侧跑完有点疼"})
show(s, "场景3: 伤病预警")

# 场景4: 连续低完成触发调整
for i in range(3):
    s = update(s, {"type": "CHECK_IN", "distance_km": 0.5, "pace": "900", "feel": "跑不动"})
    s = update(s, {"type": "CONFIRM_CHECK_IN"})
show(s, "场景4: 连续3次低完成 触发减量警告")

# 展示第1周课表
show(s, "当前状态总览")
