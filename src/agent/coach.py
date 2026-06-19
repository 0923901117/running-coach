"""
跑步教练智能体 — LangChain 核心
基于意图识别的路由架构：摸底 / 打卡 / 问答 / 伤病
"""
import os
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    import streamlit as st
    DEEPSEEK_API_KEY = st.secrets.get("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY"))
    DEEPSEEK_BASE_URL = st.secrets.get("DEEPSEEK_BASE_URL", os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"))
except:
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

# ── 配置 ────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "src" / "templates"
KNOWLEDGE_DIR = BASE_DIR / "src" / "knowledge"

LLM = ChatOpenAI(
    model="deepseek-chat",
    api_key=DEEPSEEK_API_KEY,
    base_url=DEEPSEEK_BASE_URL,
    temperature=0.7,
    max_tokens=1024,
)

# ── 系统提示词 ──────────────────────────────────

SYSTEM_PROMPT = """你是一个专业的跑步教练 AI，专门帮助跑步新手从零开始安全、科学地达成跑步目标。

## 你的角色
- 友好、鼓励但专业，像一位耐心的私人教练
- 用口语化的中文交流，适当使用 emoji 增加亲切感
- 绝不鼓励带伤训练，安全永远是第一位

## 你的能力
1. **摸底评估**：通过对话收集跑者的目标、体能、可用时间、身体情况
2. **生成训练计划**：基于跑者信息，匹配训练模板并个性化调整
3. **打卡追踪**：接收训练记录，计算进度，必要时调整计划
4. **伤病预警**：识别伤痛描述，分级给出建议（关注/减量/停跑）
5. **知识问答**：回答跑步相关的各类问题（伤痛、装备、营养、技术）

## 交互规范
- 摸底时每次只问 1-2 个问题，不要让新手感到压力
- 打卡时回显解析结果让用户确认
- 伤病相关问题时，先判断严重程度，分级响应，并声明「我是 AI 教练，不是医生」
- 输出训练计划时用结构化的格式，方便阅读

## 训练原则
- 新手遵循「渐进超负荷」原则，周增幅不超过 10%
- 跑前必须热身，跑后必须拉伸
- 每周至少安排 2-3 个休息日
- 力量训练和间歇训练在训练中期（第3-4周起）渐进引入
"""

# ── 意图识别 ────────────────────────────────────

INTENT_PROMPT = """判断用户输入属于以下哪种意图，只回复一个字母：

A - 首次摸底：用户表达了跑步意愿或目标，需要开始评估
B - 打卡记录：用户汇报了训练数据（距离、配速等）
C - 知识问答：用户问了一个跑步相关的知识问题
D - 伤病报告：用户描述了身体不适或疼痛
E - 其他/闲聊

用户输入：{user_input}
意图："""

def detect_intent(user_input: str) -> str:
    """识别用户意图"""
    prompt = INTENT_PROMPT.format(user_input=user_input[:200])
    result = LLM.invoke(prompt).content.strip().upper()
    for c in result:
        if c in "ABCDE":
            return c
    return "E"

# ── 训练计划生成器 ──────────────────────────────

def load_templates() -> dict:
    """加载训练模板"""
    with open(TEMPLATES_DIR / "plans.json", "r", encoding="utf-8-sig") as f:
        return json.load(f)

def pick_template(goal_distance_km: float) -> str:
    """根据目标距离匹配合适模板"""
    if goal_distance_km <= 3:
        return "6周入门3公里"
    elif goal_distance_km <= 5:
        return "8周入门5公里"
    elif goal_distance_km <= 10:
        return "10周入门10公里"
    else:
        return "12周半马入门"

def generate_plan_text(runner_info: dict) -> str:
    """基于跑者信息生成训练计划的文本描述"""
    templates = load_templates()
    template_name = pick_template(runner_info.get("goal_distance_km", 5))
    tmpl = templates["templates"][template_name]
    modules = templates["module_config"]
    prog = templates["progression"]

    lines = []
    lines.append(f"## {runner_info.get('name', '跑者')} 的训练计划")
    lines.append(f"")
    lines.append(f"- **目标**：{runner_info.get('goal_deadline_weeks', 8)} 周完成 {runner_info.get('goal_distance_km', 5)} 公里")
    lines.append(f"- **模板**：{template_name}")
    lines.append(f"- **每周训练**：{tmpl['sessions_per_week']} 次")
    lines.append(f"- **原则**：每周增幅 ≤ {prog['weekly_increase_pct']}%")
    lines.append(f"")

    # 按周展示
    fitness = runner_info.get("fitness_level", "zero")
    base_minutes = {"zero": 15, "beginner": 20, "intermediate": 25}.get(fitness, 15)

    for w in range(tmpl["weeks"]):
        week_num = w + 1
        lines.append(f"### 第 {week_num} 周")
        schedule = tmpl["schedule"][w]
        day_names = ["一", "二", "三", "四", "五", "六", "日"]

        for d, session_type in enumerate(schedule):
            day_label = day_names[d]
            if session_type == "rest":
                lines.append(f"- **周{day_label}** 🛌 休息日")
            elif session_type == "run":
                minutes = int(base_minutes * (1 + w * 0.1 * (prog["weekly_increase_pct"] / 10)))
                distance_est = round(minutes / 7, 1)
                lines.append(f"- **周{day_label}** 🏃 跑步 {minutes} 分钟（约 {distance_est} km）配速：轻松跑")
                lines.append(f"  - 🔥 **跑前热身（5分钟）**：")
                lines.append(f"    1. 开合跳 30秒×2组")
                lines.append(f"    2. 高抬腿 30秒×2组")
                lines.append(f"    3. 踢臀跑 30秒×2组")
                lines.append(f"    4. 弓步转体 每侧30秒")
                lines.append(f"    5. 踝关节环绕 每侧30秒")
                lines.append(f"  - 🧘 **跑后拉伸（10分钟）**：")
                lines.append(f"    1. 大腿前侧拉伸 每侧30秒×2组")
                lines.append(f"    2. 大腿后侧拉伸 每侧30秒×2组")
                lines.append(f"    3. 小腿拉伸 每侧30秒×2组")
                lines.append(f"    4. 髋屈肌拉伸 每侧30秒×2组")
                lines.append(f"    5. 臀部拉伸 每侧30秒×2组")
                lines.append(f"    6. 婴儿式放松 30秒×2组")

        # 第3周起加入力量
        if week_num >= prog["strength_start_week"]:
            lines.append(f"- 💪 **力量训练日（约20分钟）**：")
            lines.append(f"    1. 深蹲 3组×15次")
            lines.append(f"    2. 弓步蹲 每侧3组×12次")
            lines.append(f"    3. 提踵 3组×20次")
            lines.append(f"    4. 臀桥 3组×15次")
            lines.append(f"    5. 平板支撑 3组×30秒")

        # 第4周起加入 VO2max 和乳酸耐受
        if week_num >= prog["vo2max_start_week"]:
            lines.append(f"- 💨 **间歇训练日（VO2max）**：")
            lines.append(f"    - 400m 快跑 + 200m 慢跑恢复，重复4组")
            lines.append(f"    - 跑前热身5分钟 + 跑后拉伸10分钟")
        if week_num >= prog["lactate_start_week"]:
            lines.append(f"- 🔥 **节奏跑日（乳酸耐受）**：")
            lines.append(f"    - 轻松跑5分钟热身 → 阈值跑{15 + w * 2}分钟 → 轻松跑5分钟冷身")
            lines.append(f"    - 阈值配速：比5公里比赛配速慢15-20秒/公里")

        lines.append("")

    return "\n".join(lines)

# ── 伤病预警 ────────────────────────────────────

INJURY_BODY_PARTS = {
    "膝盖": "膝关节",
    "脚踝": "踝关节",
    "跟腱": "跟腱",
    "胫骨": "小腿胫骨",
    "足底": "足底筋膜",
    "脚掌": "足部",
    "小腿": "小腿肌肉",
    "大腿": "大腿肌肉",
    "髋": "髋关节",
    "臀部": "臀部肌肉",
    "腰": "下背部/腰椎",
    "背": "背部",
    "肩膀": "肩部",
    "脖子": "颈部",
}

INJURY_SENSATIONS = {
    "撕裂": "撕裂感",
    "抽筋": "抽筋",
    "痉挛": "痉挛",
    "肿": "肿胀",
    "麻": "麻木",
    "胀": "胀痛",
    "僵": "僵硬",
    "响": "弹响",
    "软": "无力/发软",
    "刺": "刺痛",
    "酸": "酸痛",
    "疼": "疼痛",
    "痛": "疼痛",
}

# 严重级别判断关键词
DANGER_SIGNS = ["动不了", "不能走", "肿了", "肿起来", "变形", "撕裂", "咔嚓", "不敢碰", "不能弯"]
WARN_SIGNS = ["疼了几天", "一直疼", "每次跑都疼", "越跑越疼", "跑完还疼", "影响跑步"]

CHECK_INJURY_PROMPT = """你是一位经验丰富的跑步教练。跑者向你描述了身体不适。

跑者描述：{symptom}
涉及部位：{body_parts}
疼痛特征：{sensations}

请以教练的口吻回复，要求：
1. 先表达关心（"听到这个我很担心"之类的）
2. 分析可能是什么问题（1-2句话，不要武断诊断）
3. 给出明确的处理建议（休息几天、冰敷、拉伸、力量训练等）
4. 根据情况给出：可以继续但要调整 / 建议暂停几天 / 建议尽快就医
5. 最后必须声明「我只是AI教练，不是医生。如果症状持续或加重，请一定去看医生。」

回复要温暖、专业、实用，不要太长（200字以内）。"""

def detect_injury_signals(symptom: str) -> tuple:
    """检测伤病信号：部位 + 感觉 + 严重级别"""
    body_parts_found = []
    for keyword, name in INJURY_BODY_PARTS.items():
        if keyword in symptom:
            body_parts_found.append(name)

    sensations_found = []
    for keyword, name in INJURY_SENSATIONS.items():
        if keyword in symptom:
            sensations_found.append(name)

    # 判断严重级别
    level = "info"
    for sign in DANGER_SIGNS:
        if sign in symptom:
            level = "danger"
            break
    if level != "danger":
        for sign in WARN_SIGNS:
            if sign in symptom:
                level = "warn"
                break

    return (
        "、".join(body_parts_found) if body_parts_found else "未明确",
        "、".join(sensations_found) if sensations_found else "未描述",
        level,
    )

def check_injury(symptom: str) -> str:
    """伤病预警：全面检测 + LLM 分析"""
    body_parts, sensations, level = detect_injury_signals(symptom)

    # 危险信号 — 立即就医提示前置
    if level == "danger":
        prefix = "⚠️ **这是需要重视的信号！**\n\n"
    elif level == "warn":
        prefix = "🟠 我注意到你描述的问题需要关注。\n\n"
    else:
        prefix = ""

    prompt = CHECK_INJURY_PROMPT.format(
        symptom=symptom,
        body_parts=body_parts,
        sensations=sensations,
    )
    result = LLM.invoke(prompt).content.strip()

    return prefix + result

# ── RAG 知识问答 ────────────────────────────────

_faiss_db = None

def _get_vectorstore():
    """懒加载 FAISS 向量库（降级安全）"""
    global _faiss_db
    if _faiss_db is not None:
        return _faiss_db

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_community.vectorstores import FAISS
        import os as _os
        _os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

        embeddings = HuggingFaceEmbeddings(
            model_name="shibing624/text2vec-base-chinese",
            cache_folder="/tmp/hf_cache" if _os.path.exists("/tmp") else None,
        )

        faiss_path = Path.home() / ".running_coach_faiss"
        if faiss_path.exists():
            _faiss_db = FAISS.load_local(str(faiss_path), embeddings, allow_dangerous_deserialization=True)
        else:
            _faiss_db = None
    except Exception as e:
        _faiss_db = None

    return _faiss_db

QA_PROMPT = """你是一个跑步教练。根据以下参考资料回答用户问题。如果资料不足以回答，诚实说明并给出你的专业建议。

参考资料：
{context}

用户问题：{question}

回答（简洁专业，100-200字）："""

def answer_knowledge(question: str) -> str:
    """RAG 知识问答"""
    vectorstore = _get_vectorstore()

    if vectorstore is None:
        # 降级：直接用 LLM 回答
        prompt = QA_PROMPT.format(context="（无参考资料，请依靠你的跑步专业知识回答）", question=question)
        return LLM.invoke(prompt).content.strip()

    docs = vectorstore.similarity_search(question, k=3)
    context = "\n\n".join([d.page_content for d in docs])
    prompt = QA_PROMPT.format(context=context, question=question)
    return LLM.invoke(prompt).content.strip()

# ── 主对话函数 ──────────────────────────────────

def chat(user_input: str, history: list = None, runner_info: dict = None) -> dict:
    """
    主对话入口
    返回 {"reply": str, "runner_info": dict, "intent": str}
    """
    if history is None:
        history = []
    if runner_info is None:
        runner_info = {}

    intent = detect_intent(user_input)

    # 构建消息
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
    for h in history[-6:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_input))

    # 根据意图选择回复策略
    if intent == "A":
        reply = _handle_assessment(user_input, messages, runner_info)
    elif intent == "B":
        reply = _handle_checkin(user_input, runner_info)
    elif intent == "C":
        reply = answer_knowledge(user_input)
    elif intent == "D":
        reply = check_injury(user_input)
    else:
        reply = LLM.invoke(messages).content.strip()

    return {"reply": reply, "runner_info": runner_info, "intent": intent}

# ── 摸底评估处理 ────────────────────────────────

EXTRACT_GOAL_PROMPT = """从用户输入中提取跑步目标信息，返回 JSON：
{{"goal_distance_km": 数字或null, "goal_deadline_weeks": 数字或null, "description": "原始描述"}}

输入：{user_input}
JSON："""

EXTRACT_FITNESS_PROMPT = """从用户输入中提取跑步体能信息，返回 JSON：
{{"fitness_level": "zero"/"beginner"/"intermediate"/null, "available_days": 数字或null}}

输入：{user_input}
JSON："""

EXTRACT_BODY_PROMPT = """从用户输入中提取身体信息，返回 JSON：
{{"age": 数字或null, "weight": 数字(kg)或null, "injuries": ["旧伤列表"]}}

输入：{user_input}
JSON："""

def _handle_assessment(user_input: str, messages: list, runner_info: dict) -> str:
    """处理摸底评估对话 — 提取信息 + 引导下一步"""
    ri = runner_info

    # Step 1: 提取目标
    if not ri.get("goal_distance_km"):
        try:
            prompt = EXTRACT_GOAL_PROMPT.format(user_input=user_input)
            data = json.loads(LLM.invoke(prompt).content.strip())
            if data.get("goal_distance_km") and data.get("goal_deadline_weeks"):
                ri["goal_distance_km"] = data["goal_distance_km"]
                ri["goal_deadline_weeks"] = data["goal_deadline_weeks"]
                return f"""收到！目标：{data['goal_deadline_weeks']}周完成{data['goal_distance_km']}公里 ✅

接下来：你现在的跑步基础怎么样？最远跑过多远？以前有运动习惯吗？"""
        except:
            pass
        return "欢迎！我是你的跑步教练 🏃 先告诉我：你想达成什么目标？比如「2个月跑5公里」"

    # Step 2: 提取体能
    if not ri.get("fitness_level"):
        try:
            prompt = EXTRACT_FITNESS_PROMPT.format(user_input=user_input)
            data = json.loads(LLM.invoke(prompt).content.strip())
            level = data.get("fitness_level")
            days = data.get("available_days")
            if level:
                ri["fitness_level"] = level
                ri["available_days"] = days or 3
                level_names = {"zero": "零基础", "beginner": "入门", "intermediate": "进阶"}
                return f"""明白了！你的基础：{level_names.get(level, level)}，每周可用{ri['available_days']}天 ✅

最后一步：方便告诉我年龄、体重吗？有没有旧伤（比如膝盖、脚踝）？"""
        except:
            pass
        return "好的，你的跑步基础怎么样？是零基础从没跑过，还是已经能跑个一两公里了？每周能抽出几天训练？"

    # Step 3: 提取身体信息
    if not ri.get("age"):
        try:
            prompt = EXTRACT_BODY_PROMPT.format(user_input=user_input)
            data = json.loads(LLM.invoke(prompt).content.strip())
            age = data.get("age")
            weight = data.get("weight")
            if age or weight:
                ri["age"] = age or 0
                ri["weight"] = weight or 0
                ri["injuries"] = data.get("injuries", [])
                injuries_str = "、".join(ri["injuries"]) if ri["injuries"] else "无"
                return f"""收到！{ri['age']}岁，{ri['weight']}kg，旧伤：{injuries_str} ✅

📋 **信息收集完毕！** 给你整理一下：
- 目标：{ri['goal_deadline_weeks']}周{ri['goal_distance_km']}公里
- 水平：{ri['fitness_level']}，每周{ri['available_days']}天
- 身体：{ri['age']}岁/{ri['weight']}kg

回复「**生成计划**」我马上给你出训练方案！"""
        except:
            pass
        return "最后一步啦～年龄和体重是多少？有没有旧伤？"

    # 信息齐全
    return f"""你的信息已经齐全了 ✅

- 目标：{ri['goal_deadline_weeks']}周{ri['goal_distance_km']}公里
- 水平：{ri['fitness_level']}，每周{ri['available_days']}天

回复「**生成计划**」即可查看你的专属训练方案！"""

# ── 打卡处理 ────────────────────────────────────

CHECKIN_PARSE_PROMPT = """从用户输入中提取跑步训练数据，返回 JSON：
{{"distance_km": 数字, "pace": "配速描述", "feel": "体感描述", "is_checkin": true/false}}
如果明显不是打卡数据，is_checkin 为 false。

输入：{user_input}
JSON："""

def _handle_checkin(user_input: str, runner_info: dict) -> str:
    """处理打卡"""
    prompt = CHECKIN_PARSE_PROMPT.format(user_input=user_input)
    try:
        data = json.loads(LLM.invoke(prompt).content.strip())
    except json.JSONDecodeError:
        return "我没太理解你的训练数据，可以说详细一点吗？比如「今天跑了 3 公里，配速 7 分，感觉还行」"

    if not data.get("is_checkin", True):
        return "收到！不过看起来不太像训练打卡，想聊聊别的吗？"

    distance = data.get("distance_km", 0)
    pace = data.get("pace", "未知")
    feel = data.get("feel", "未描述")

    return f"""📊 **打卡记录解析**

- 距离：{distance} km
- 配速：{pace}
- 体感：{feel}

如果确认无误请回复「确认」，如需修改请重新描述。"""


print("coach agent loaded")
