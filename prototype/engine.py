"""
PROTOTYPE — 跑步教练智能体 纯状态引擎
问题：「摸底→计划→打卡→进度→调整 这条状态链路走得通吗？」

纯函数模块：无 I/O，无终端代码，可直接复用到正式实现。
"""

from dataclasses import dataclass, field
from typing import Optional
from copy import deepcopy
from enum import Enum
import json

# ── 领域类型 ────────────────────────────────────

class Phase(Enum):
    IDLE       = "idle"        # 等待开始
    ASSESSING  = "assessing"   # 摸底评估中
    ACTIVE     = "active"      # 训练进行中
    COMPLETED  = "completed"   # 计划完成

class AlertLevel(Enum):
    INFO   = "info"     # 建议关注
    WARN   = "warn"     # 建议减量
    DANGER = "danger"   # 建议停跑就医

@dataclass
class Runner:
    name: str = ""
    age: int = 0
    weight: float = 0.0
    fitness_level: str = ""          # zero / beginner / intermediate
    available_days: int = 3
    goal_distance_km: float = 0.0
    goal_deadline_weeks: int = 0
    injuries: list = field(default_factory=list)

@dataclass
class Session:
    day: int
    type: str               # run / rest / warmup / stretch / strength / vo2max / lactate
    params: dict = field(default_factory=dict)
    completed: bool = False
    record: Optional[dict] = None  # {distance_km, pace, feel}

@dataclass
class Week:
    week: int
    sessions: list = field(default_factory=list)

@dataclass
class Progress:
    current_week: int = 1
    current_day: int = 1
    total_sessions: int = 0
    completed_sessions: int = 0
    consecutive_under: int = 0
    consecutive_over: int = 0

@dataclass
class State:
    phase: Phase = Phase.IDLE
    runner: Runner = field(default_factory=Runner)
    plan: list = field(default_factory=list)        # list[Week]
    progress: Progress = field(default_factory=Progress)
    injury_alerts: list = field(default_factory=list)
    messages: list = field(default_factory=list)    # 系统消息
    pending_confirmation: Optional[dict] = None     # 打卡待确认数据

# ── 训练模板 ────────────────────────────────────

TEMPLATES = {
    "6周入门3公里": {
        "weeks": 6,
        "sessions_per_week": 3,
        "default_distance": 3.0,
        "pattern": [
            ["run","rest","run","rest","run","rest","rest"],
        ] * 6,
    },
    "8周入门5公里": {
        "weeks": 8,
        "sessions_per_week": 3,
        "default_distance": 5.0,
        "pattern": [
            ["run","rest","run","rest","run","rest","rest"],
        ] * 8,
    },
    "10周入门10公里": {
        "weeks": 10,
        "sessions_per_week": 3,
        "default_distance": 10.0,
        "pattern": [
            ["run","rest","run","rest","run","rest","rest"],
        ] * 10,
    },
    "12周半马入门": {
        "weeks": 12,
        "sessions_per_week": 4,
        "default_distance": 21.1,
        "pattern": [
            ["run","rest","run","rest","run","rest","run"],
        ] * 12,
    },
}

# ── 伤病关键词映射 ──────────────────────────────

INJURY_KEYWORDS = {
    "膝盖外侧": ("髂胫束综合征", AlertLevel.WARN),
    "膝盖前侧": ("髌骨关节疼痛", AlertLevel.WARN),
    "跟腱":     ("跟腱炎", AlertLevel.WARN),
    "胫骨":     ("胫骨骨膜炎", AlertLevel.WARN),
    "足底":     ("足底筋膜炎", AlertLevel.WARN),
    "刺痛":     ("不明原因刺痛", AlertLevel.DANGER),
    "肿":       ("关节肿胀", AlertLevel.DANGER),
    "动不了":   ("活动受限", AlertLevel.DANGER),
    "脚踝":     ("踝关节不适", AlertLevel.INFO),
    "小腿":     ("小腿肌肉酸痛", AlertLevel.INFO),
}

# ── Reducer ──────────────────────────────────────

def init_state() -> State:
    """返回初始状态"""
    return State()

def update(state: State, action: dict) -> State:
    """(State, Action) => State 纯 reducer"""
    s = deepcopy(state)
    action_type = action.get("type")

    # ── 开始摸底 ──
    if action_type == "START_ASSESSMENT":
        s.phase = Phase.ASSESSING
        s.messages.append("🏃 欢迎！我是你的跑步教练。咱们先来了解你的情况。")
        s.messages.append("你想达成什么目标？比如「2个月跑5公里」")

    # ── 设置目标 ──
    elif action_type == "SET_GOAL":
        s.runner.goal_distance_km = action["distance_km"]
        s.runner.goal_deadline_weeks = action["deadline_weeks"]
        s.messages.append(f"目标: {action['deadline_weeks']}周完成{action['distance_km']}公里 ✅")
        s.messages.append("你现在的跑步水平？最远跑过多远、什么配速？")

    # ── 设置体能 ──
    elif action_type == "SET_FITNESS":
        level = action["level"]
        s.runner.fitness_level = level
        s.runner.available_days = action.get("available_days", 3)
        s.messages.append(f"当前水平: {level}，每周可用 {s.runner.available_days} 天 ✅")
        s.messages.append("你的年龄、体重？有没有旧伤？")

    # ── 设置身体信息 ──
    elif action_type == "SET_BODY_INFO":
        s.runner.age = action["age"]
        s.runner.weight = action["weight"]
        s.runner.injuries = action.get("injuries", [])
        s.messages.append(f"年龄{action['age']}岁, 体重{action['weight']}kg ✅")
        s.messages.append("信息收集完毕！[G] 一键生成训练计划")

    # ── 生成计划 ──
    elif action_type == "GENERATE_PLAN":
        s = _generate_plan(s)

    # ── 打卡（待确认） ──
    elif action_type == "CHECK_IN":
        # 检查下一个待训练 session 是不是休息日
        TRAINING_TYPES = {"run", "vo2max", "lactate", "strength", "warmup", "stretch"}
        prog = s.progress
        w, d = prog.current_week, prog.current_day
        if w <= len(s.plan):
            week = s.plan[w - 1]
            if d <= len(week.sessions):
                ses = week.sessions[d - 1]
                if ses.type == "rest":
                    s.messages.append(f"🛌 今天是休息日！好好恢复，第{w}周第{d}天不需要训练。")
                    return s
        s.pending_confirmation = {
            "distance_km": action["distance_km"],
            "pace": action["pace"],
            "feel": action["feel"],
        }
        record = s.pending_confirmation
        s.messages.append(
            f"收到：{record['distance_km']}km, 配速{record['pace']}, 体感「{record['feel']}」"
        )
        s.messages.append("确认吗？[Y] 确认 [N] 修改")

    # ── 确认打卡 ──
    elif action_type == "CONFIRM_CHECK_IN":
        if s.pending_confirmation is None:
            s.messages.append("⚠️ 没有待确认的打卡")
            return s
        s = _apply_check_in(s, s.pending_confirmation)
        s.pending_confirmation = None

    # ── 取消打卡 ──
    elif action_type == "CANCEL_CHECK_IN":
        s.pending_confirmation = None
        s.messages.append("已取消，请重新输入")

    # ── 伤病报告 ──
    elif action_type == "REPORT_INJURY":
        symptom = action["symptom"]
        alert = _check_injury(symptom)
        s.injury_alerts.append(alert)
        s.messages.append(f"🩺 伤病预警: [{alert['level']}] {alert['diagnosis']} — {alert['advice']}")

    # ── 查看当前周 ──
    elif action_type == "VIEW_WEEK":
        pass  # TUI 自己读 state

    return s


# ── 内部纯函数 ──────────────────────────────────

def _pick_template(runner: Runner) -> str:
    """根据目标选模板"""
    d = runner.goal_distance_km
    if d <= 3: return "6周入门3公里"
    if d <= 5: return "8周入门5公里"
    if d <= 10: return "10周入门10公里"
    return "12周半马入门"

def _generate_plan(state: State) -> State:
    """从模板生成训练计划"""
    s = state
    template_name = _pick_template(s.runner)
    tmpl = TEMPLATES[template_name]

    # 按目标和水平调整每周跑量
    if s.runner.fitness_level == "zero":
        base_minutes = 15
    elif s.runner.fitness_level == "beginner":
        base_minutes = 20
    else:
        base_minutes = 25

    s.plan = []
    total_sessions = 0
    for w in range(tmpl["weeks"]):
        week_sessions = []
        for d, day_type in enumerate(tmpl["pattern"][w]):
            session = Session(day=d + 1, type=day_type)
            if day_type == "run":
                # 渐进：每周增加 10%
                minutes = int(base_minutes * (1 + w * 0.1))
                session.params = {"minutes": minutes, "pace": "轻松跑"}
                total_sessions += 1
            elif day_type == "rest":
                session.params = {"description": "休息日，好好恢复"}
            week_sessions.append(session)

        # 第4周起在后半段跑日附加 VO2max 或 乳酸耐受
        if w >= 3:
            run_days = [s for s in week_sessions if s.type == "run"]
            if len(run_days) >= 2:
                # 倒数第2个跑日 → 乳酸耐受
                run_days[-2].type = "lactate"
                run_days[-2].params = {"minutes": int(base_minutes * 1.1 * (1 + w * 0.1)), "pace": "阈值跑"}
                # 最后一个跑日 → VO2max 间歇
                run_days[-1].type = "vo2max"
                run_days[-1].params = {"intervals": "4x400m", "pace": "间歇"}

        # 附加热身和拉伸
        for session in week_sessions:
            if session.type == "run":
                session.params["warmup"] = "动态拉伸5分钟：开合跳、高抬腿、踢臀跑"
                session.params["stretch"] = "跑后拉伸：大腿前侧30s×2、大腿后侧30s×2、小腿30s×2、髋屈肌30s×2"

        # 第3周起附加力量日
        if w >= 2:
            strength_day = Week(week=w+1, sessions=[
                Session(day=0, type="strength", params={"exercises": "深蹲3x15、弓步蹲3x12、提踵3x20、臀桥3x15"})
            ])
            # 插入到第一个休息日前
            for i, ses in enumerate(week_sessions):
                if ses.type == "rest":
                    week_sessions[i] = Session(day=ses.day, type="strength", params={"exercises": "深蹲3x15、弓步蹲3x12、提踵3x20、臀桥3x15"})
                    break

        s.plan.append(Week(week=w + 1, sessions=week_sessions))

    s.progress.total_sessions = total_sessions
    s.phase = Phase.ACTIVE
    s.messages.append(f"📋 加载模板: {template_name}")
    s.messages.append(f"📅 共 {tmpl['weeks']} 周，{total_sessions} 次跑步训练")
    s.messages.append("训练计划已生成！输入 [C 距离 配速 体感] 打卡")
    return s

def _apply_check_in(state: State, record: dict) -> State:
    """应用一次打卡，更新进度并检查是否需要调整"""
    s = state
    prog = s.progress

    # 找到当前周当前天的 session（跳过休息日）
    TRAINING_TYPES = {"run", "vo2max", "lactate", "strength", "warmup", "stretch"}

    def _find_next_training_session(s):
        """从当前进度位置找下一个训练日，跳过休息日"""
        w = prog.current_week
        d = prog.current_day
        while w <= len(s.plan):
            week = s.plan[w - 1]
            while d <= len(week.sessions):
                ses = week.sessions[d - 1]
                if ses.type in TRAINING_TYPES and not ses.completed:
                    prog.current_week = w
                    prog.current_day = d
                    return ses
                d += 1
            w += 1
            d = 1
        return None

    session = _find_next_training_session(s)

    if session is None:
        s.messages.append("🏁 计划已全部完成！")
        s.phase = Phase.COMPLETED
        return s

    # 完成打卡
    session.completed = True
    session.record = record
    prog.completed_sessions += 1

    s.messages.append(f"✅ 第{prog.current_week}周第{prog.current_day}天打卡成功！")

    # 评估完成度（只对跑步类型计算）
    RUN_TYPES = {"run", "vo2max", "lactate"}
    if session.type in RUN_TYPES and "minutes" in session.params:
        expected_minutes = session.params["minutes"]
        actual_distance = record["distance_km"]
        # 新手配速约 6-8 分/km，取 7 分估算
        expected_distance = expected_minutes / 7.0
        if expected_distance > 0:
            estimated_completion = min(actual_distance / expected_distance * 100, 200)
        else:
            estimated_completion = 100
    else:
        estimated_completion = 100

    if estimated_completion < 60:
        prog.consecutive_under += 1
        prog.consecutive_over = 0
    elif estimated_completion > 120:
        prog.consecutive_over += 1
        prog.consecutive_under = 0
    else:
        prog.consecutive_under = 0
        prog.consecutive_over = 0

    # 动态调整
    if prog.consecutive_under >= 2:
        s.messages.append("⚠️ 连续两次未达标，建议下周减量10%")
    elif prog.consecutive_over >= 2:
        s.messages.append("📈 连续两次超额完成，下周适度加量10%")
    elif estimated_completion > 150:
        s.messages.append("⚠️ 加量太快容易受伤，建议控制节奏！")

    # 推进到下一个训练 session
    prog.current_day += 1
    next_session = _find_next_training_session(s)

    if next_session is None:
        s.messages.append("🎉 恭喜完成全部训练计划！")
        s.phase = Phase.COMPLETED

    return s

def _check_injury(symptom: str) -> dict:
    """关键词匹配 + 分级"""
    for keyword, (diagnosis, level) in INJURY_KEYWORDS.items():
        if keyword in symptom:
            advice_map = {
                AlertLevel.INFO: "可以继续训练但注意观察",
                AlertLevel.WARN: "建议减量或休息，如持续请就医",
                AlertLevel.DANGER: "建议立即停跑，尽快就医",
            }
            return {
                "symptom": symptom,
                "diagnosis": diagnosis,
                "level": level.name,
                "advice": advice_map[level],
            }
    return {
        "symptom": symptom,
        "diagnosis": "无法自动识别，建议咨询专业医生",
        "level": AlertLevel.WARN.name,
        "advice": "不确定的情况建议谨慎，可先休息观察",
    }


# ── 辅助 ──

def state_to_dict(state: State) -> dict:
    """状态序列化为纯 dict（方便 TUI 渲染）"""
    return {
        "phase": state.phase.value,
        "runner": {
            "name": state.runner.name,
            "age": state.runner.age,
            "weight": state.runner.weight,
            "fitness_level": state.runner.fitness_level,
            "available_days": state.runner.available_days,
            "goal": f"{state.runner.goal_deadline_weeks}周{state.runner.goal_distance_km}km",
            "injuries": state.runner.injuries,
        },
        "plan": [
            {
                "week": w.week,
                "sessions": [
                    {
                        "day": s.day, "type": s.type,
                        "params": s.params, "completed": s.completed,
                        "record": s.record,
                    }
                    for s in w.sessions
                ]
            }
            for w in state.plan
        ],
        "progress": {
            "current_week": state.progress.current_week,
            "current_day": state.progress.current_day,
            "total_sessions": state.progress.total_sessions,
            "completed_sessions": state.progress.completed_sessions,
            "consecutive_under": state.progress.consecutive_under,
            "consecutive_over": state.progress.consecutive_over,
            "completion_pct": round(state.progress.completed_sessions / max(state.progress.total_sessions, 1) * 100, 1),
        },
        "injury_alerts": state.injury_alerts,
        "messages": state.messages[-5:],  # 最近5条
        "pending_confirmation": state.pending_confirmation,
    }


print("engine loaded — prototype pure logic module")
