"""
PROTOTYPE — 跑步教练智能体 终端 TUI
纯交互层：导入 engine，驱动状态变化，每帧全屏重绘。
运行: python prototype/run.py
"""

import os
import sys
from engine import (
    State, Phase, init_state, update, state_to_dict,
    TEMPLATES, INJURY_KEYWORDS,
)

BOLD   = "\x1b[1m"
DIM    = "\x1b[2m"
GREEN  = "\x1b[32m"
YELLOW = "\x1b[33m"
RED    = "\x1b[31m"
CYAN   = "\x1b[36m"
MAGENTA = "\x1b[35m"
RESET  = "\x1b[0m"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def render(state: State):
    """渲染全帧"""
    s = state_to_dict(state)

    print(f"{BOLD}{CYAN}╔══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║       🏃 跑步教练智能体 — 原型验证            ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════╝{RESET}")
    print()

    # ── 阶段指示 ──
    phase_colors = {"idle": DIM, "assessing": YELLOW, "active": GREEN, "completed": MAGENTA}
    pc = phase_colors.get(s["phase"], "")
    print(f"{BOLD}阶段:{RESET} {pc}{s['phase']}{RESET}")

    # ── 跑者信息 ──
    if s["phase"] != "idle":
        r = s["runner"]
        print()
        print(f"{BOLD}跑者信息:{RESET}")
        if r.get("age"):    print(f"  年龄: {r['age']}岁  体重: {r['weight']}kg")
        if r.get("fitness_level"): print(f"  水平: {r['fitness_level']}  可用天数: {r['available_days']}")
        if r.get("goal"):   print(f"  目标: {r['goal']}")
        if r.get("injuries"): print(f"  旧伤: {', '.join(r['injuries'])}")

    # ── 进度 ──
    if s["phase"] == "active" or s["phase"] == "completed":
        print()
        p = s["progress"]
        bar_len = 20
        filled = int(bar_len * p["completion_pct"] / 100)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"{BOLD}进度:{RESET} [{bar}] {p['completion_pct']}%")
        print(f"  第{p['current_week']}周 第{p['current_day']}天 | "
              f"完成 {p['completed_sessions']}/{p['total_sessions']}")
        if p["consecutive_under"]:
            print(f"  {YELLOW}⚠ 连续未达标: {p['consecutive_under']}次{RESET}")
        if p["consecutive_over"]:
            print(f"  {GREEN}📈 连续超额: {p['consecutive_over']}次{RESET}")

    # ── 当前周训练表 ──
    if s["plan"] and s["phase"] in ("active", "completed"):
        print()
        current_week = min(s["progress"]["current_week"], len(s["plan"]))
        week = s["plan"][current_week - 1]
        print(f"{BOLD}第{current_week}周训练表:{RESET}")
        for ses in week["sessions"]:
            status = f"{GREEN}✓{RESET}" if ses["completed"] else f"{DIM}○{RESET}"
            type_icon = {"run":"🏃","rest":"💤","warmup":"🔥","stretch":"🧘",
                         "strength":"🏋️","vo2max":"💨","lactate":"🔥"}.get(ses["type"],"❓")
            params_str = str(ses["params"]).replace("{","").replace("}","").replace("'","")[:40]
            print(f"  D{ses['day']} {type_icon} {ses['type']:8s} {status}  {DIM}{params_str}{RESET}")

    # ── 伤病预警 ──
    if s["injury_alerts"]:
        print()
        print(f"{BOLD}🩺 伤病预警:{RESET}")
        for a in s["injury_alerts"][-3:]:
            lc = {"info": YELLOW, "warn": RED, "danger": RED + BOLD}.get(a["level"], "")
            print(f"  {lc}[{a['level'].upper()}]{RESET} {a['diagnosis']} — {a['advice']}")

    # ── 消息 ──
    if s["messages"]:
        print()
        print(f"{BOLD}最近消息:{RESET}")
        for msg in s["messages"]:
            print(f"  {msg}")

    # ── 操作区 ──
    print()
    print(f"{BOLD}{CYAN}── 操作 ──────────────────────────────────────────{RESET}")
    _render_controls(s)

def _render_controls(s: dict):
    """根据阶段显示可用操作"""
    phase = s["phase"]
    instructions = []

    if phase == "idle":
        instructions = [
            (f"{BOLD}[S]{RESET}", "开始摸底评估"),
        ]
    elif phase == "assessing":
        runner = s["runner"]
        if not runner.get("goal") or "0周" in runner.get("goal", ""):
            instructions = [
                (f"{BOLD}[G 距离 周数]{RESET}", f"设置目标  例: {DIM}G 5 8{RESET}"),
            ]
        elif not runner.get("fitness_level"):
            instructions = [
                (f"{BOLD}[F 水平 天数]{RESET}", f"设置体能  例: {DIM}F zero 3{RESET}"),
                (f"{DIM}水平: zero / beginner / intermediate{RESET}", ""),
            ]
        elif not runner.get("age"):
            instructions = [
                (f"{BOLD}[B 年龄 体重]{RESET}", f"设置身体  例: {DIM}B 25 65{RESET}"),
                (f"[B 年龄 体重 旧伤1 旧伤2]", "选择性地添加旧伤"),
            ]
        else:
            instructions = [
                (f"{BOLD}[G]{RESET}", "一键生成训练计划"),
            ]
    elif phase == "active":
        instructions = [
            (f"{BOLD}[C 距离 配速 体感]{RESET}", f"打卡  例: {DIM}C 3.2 730 还行{RESET}"),
            (f"{BOLD}[I 症状]{RESET}", f"伤病报告  例: {DIM}I 膝盖外侧疼{RESET}"),
            (f"{BOLD}[V]{RESET}", "查看本周训练"),
        ]
        if s.get("pending_confirmation"):
            instructions = [
                (f"{BOLD}[Y]{RESET}", "确认打卡"),
                (f"{BOLD}[N]{RESET}", "取消打卡"),
            ]
    elif phase == "completed":
        instructions = [
            (f"{BOLD}[R]{RESET}", "重新开始"),
        ]

    instructions.append((f"{BOLD}[Q]{RESET}", "退出"))

    for key, desc in instructions:
        if desc:
            print(f"  {key}  {desc}")
        else:
            print(f"  {key}")

def main():
    state = init_state()

    while True:
        clear()
        render(state)

        try:
            raw = input(f"\n{BOLD}> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 再见！")
            break

        if not raw:
            continue

        parts = raw.split()
        cmd = parts[0].upper()

        # ── 全局命令 ──
        if cmd in ("Q", "QUIT"):
            print("👋 再见！")
            break

        if cmd in ("R", "RESET"):
            state = init_state()
            state = update(state, {"type": "START_ASSESSMENT"})
            continue

        # ── 阶段命令 ──
        if state.phase == Phase.IDLE:
            if cmd in ("S", "START"):
                state = update(state, {"type": "START_ASSESSMENT"})

        elif state.phase == Phase.ASSESSING:
            if cmd == "G":
                runner = state.runner
                if parts[0].upper() == "G" and len(parts) == 3:
                    # G 5 8
                    state = update(state, {"type": "SET_GOAL", "distance_km": float(parts[1]), "deadline_weeks": int(parts[2])})
                elif not runner.goal_distance_km:
                    state = update(state, {"type": "GENERATE_PLAN"})
                else:
                    state = update(state, {"type": "GENERATE_PLAN"})
            elif cmd == "F" and len(parts) >= 3:
                state = update(state, {
                    "type": "SET_FITNESS",
                    "level": parts[1],
                    "available_days": int(parts[2]),
                })
            elif cmd == "B" and len(parts) >= 3:
                injuries = parts[3:] if len(parts) > 3 else []
                state = update(state, {
                    "type": "SET_BODY_INFO",
                    "age": int(parts[1]),
                    "weight": float(parts[2]),
                    "injuries": injuries,
                })

        elif state.phase == Phase.ACTIVE:
            if state.pending_confirmation:
                if cmd == "Y":
                    state = update(state, {"type": "CONFIRM_CHECK_IN"})
                elif cmd == "N":
                    state = update(state, {"type": "CANCEL_CHECK_IN"})
            elif cmd == "C" and len(parts) >= 4:
                state = update(state, {
                    "type": "CHECK_IN",
                    "distance_km": float(parts[1]),
                    "pace": parts[2],
                    "feel": " ".join(parts[3:]),
                })
            elif cmd == "I" and len(parts) >= 2:
                state = update(state, {
                    "type": "REPORT_INJURY",
                    "symptom": " ".join(parts[1:]),
                })
            elif cmd == "V":
                pass  # 刷新即显示

        elif state.phase == Phase.COMPLETED:
            pass  # 只有 R/Q

    return 0

if __name__ == "__main__":
    sys.exit(main())
