import sys; sys.path.insert(0, ".")
from src.agent.coach import detect_intent, pick_template, load_templates, check_injury, INJURY_KEYWORDS

print("1. Agent 模块导入 OK")
print("2. 模板匹配 5km:", pick_template(5.0))
print("3. 模板匹配 10km:", pick_template(10.0))
print("4. 伤病关键词:", len(INJURY_KEYWORDS), "组")
print("5. 模板数量:", len(load_templates()["templates"]), "套")
print()
print("模块加载全部通过!")
