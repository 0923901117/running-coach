"""
跑步教练智能体 — Streamlit 前端界面
运行：streamlit run src/ui/app.py
"""
import sys
import json
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import json
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent.parent / "data" / "runner_data.json"

def save_runner_data(runner_info, plan_text="", plan_generated=False):
    """持久化跑者数据"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "runner_info": runner_info,
        "plan_text": plan_text,
        "plan_generated": plan_generated,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_runner_data():
    """加载持久化数据"""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

from src.agent.coach import (
    chat, generate_plan_text, load_templates, pick_template,
    detect_intent, answer_knowledge, check_injury,
)

st.set_page_config(
    page_title="跑步教练 AI",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 样式 ──
st.markdown("""
<style>
    .stApp { background: #f8fafc; }
    .main-header { font-size: 2rem; font-weight: 700; color: #1e40af; margin-bottom: 0.5rem; }
    .plan-card { background: white; border-radius: 12px; padding: 1rem; margin: 0.5rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .status-dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
    .status-online { background: #22c55e; }
    .injury-warn { background: #fef3c7; border-left: 4px solid #f59e0b; padding: 0.8rem; border-radius: 0 8px 8px 0; margin: 0.5rem 0; }
    .injury-danger { background: #fee2e2; border-left: 4px solid #ef4444; padding: 0.8rem; border-radius: 0 8px 8px 0; margin: 0.5rem 0; }
</style>
""", unsafe_allow_html=True)

# ── Session State 初始化（从文件恢复） ──
if "initialized" not in st.session_state:
    saved = load_runner_data()
    if saved:
        st.session_state.runner_info = saved.get("runner_info", {})
        st.session_state.plan_text = saved.get("plan_text", "")
        st.session_state.plan_generated = saved.get("plan_generated", False)
        st.session_state.messages = []
        if st.session_state.plan_generated:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "👋 欢迎回来！你的训练计划和进度都在，继续加油～"
            })
    else:
        st.session_state.runner_info = {}
        st.session_state.plan_text = ""
        st.session_state.plan_generated = False
        st.session_state.messages = []
    st.session_state.initialized = True

# ── 侧边栏 ──
with st.sidebar:
    st.markdown('<div class="main-header">🏃 跑步教练</div>', unsafe_allow_html=True)
    st.markdown('<span class="status-dot status-online"></span> 在线', unsafe_allow_html=True)
    st.divider()

    # 注册表单
    if not st.session_state.plan_generated:
        st.markdown("### 📝 新手注册")

        with st.form("register_form"):
            name = st.text_input("昵称", placeholder="怎么称呼你？")
            gender = st.selectbox("性别", ["男", "女"])
            col1, col2 = st.columns(2)
            with col1:
                goal_dist = st.number_input("目标距离 (km)", min_value=1.0, max_value=42.0, value=5.0, step=1.0)
            with col2:
                goal_weeks = st.number_input("目标周数", min_value=4, max_value=24, value=8, step=2)

            fitness = st.selectbox("跑步基础", ["zero", "beginner", "intermediate"],
                                   format_func=lambda x: {"zero": "零基础（没跑过）", "beginner": "入门（能跑1-3km）", "intermediate": "进阶（能跑5km+）"}[x])

            available_days = st.slider("每周训练天数", 2, 6, 3)

            col3, col4 = st.columns(2)
            with col3:
                age = st.number_input("年龄", min_value=14, max_value=80, value=25, step=1)
            with col4:
                weight = st.number_input("体重 (kg)", min_value=35.0, max_value=150.0, value=65.0, step=1.0)

            injuries = st.text_input("旧伤（选填）", placeholder="如：膝盖、脚踝，无则留空")

            submitted = st.form_submit_button("✅ 提交注册", use_container_width=True, type="primary")

            if submitted:
                st.session_state.runner_info = {
                    "name": name or "跑者",
                    "gender": gender,
                    "goal_distance_km": goal_dist,
                    "goal_deadline_weeks": goal_weeks,
                    "fitness_level": fitness,
                    "available_days": available_days,
                    "age": age,
                    "weight": weight,
                    "injuries": [i.strip() for i in injuries.split(",") if i.strip()],
                }
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"欢迎 {st.session_state.runner_info['name']}！信息已录入 ✅ 回复「**生成计划**」即可查看训练方案~"
                })
                save_runner_data(st.session_state.runner_info)
                st.rerun()
    else:
        # 已注册 — 显示档案
        st.markdown("### 跑者档案")
        ri = st.session_state.runner_info
        if ri.get("name"):
            st.write(f"**昵称**：{ri['name']}")
        if ri.get("gender"):
            st.write(f"**性别**：{ri['gender']}")
        if ri.get("goal_distance_km"):
            st.write(f"**目标**：{ri.get('goal_deadline_weeks', '?')} 周 {ri['goal_distance_km']} 公里")
        if ri.get("fitness_level"):
            level_names = {"zero": "零基础", "beginner": "入门", "intermediate": "进阶"}
            st.write(f"**水平**：{level_names.get(ri['fitness_level'], ri['fitness_level'])}")
        if ri.get("age"):
            st.write(f"**年龄/体重**：{ri['age']} 岁 / {ri['weight']} kg")
        if ri.get("injuries"):
            st.write(f"**旧伤**：{'、'.join(ri['injuries'])}")

    # 快捷操作
    st.divider()
    if st.button("🔄 重新开始", use_container_width=True):
        st.session_state.messages = []
        st.session_state.runner_info = {}
        st.session_state.plan_generated = False
        st.session_state.plan_text = ""
        if DATA_FILE.exists():
            DATA_FILE.unlink()
        st.rerun()

# ── 主布局：单选切换 ──
mode = st.radio("选择功能", ["💬 对话", "📅 训练计划"], horizontal=True)

if mode == "💬 对话":

    # 显示历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 输入框
    user_input = st.chat_input("说说你的跑步目标或问题...")

    if user_input:
        # 添加用户消息
        st.session_state.messages.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        # 处理输入
        with st.chat_message("assistant"):
            with st.spinner("教练思考中..."):
                # 特殊处理：请求生成计划
                if "生成计划" in user_input and not st.session_state.plan_generated:
                    ri = st.session_state.runner_info
                    if ri.get("goal_distance_km") and ri.get("fitness_level"):
                        plan_text = generate_plan_text(ri)
                        st.session_state.plan_text = plan_text
                        st.session_state.plan_generated = True
                        save_runner_data(st.session_state.runner_info, plan_text, True)
                        reply = "📋 训练计划已生成！查看右侧面板。告诉我准备好了就开始打卡吧~"
                    else:
                        reply = "信息还不够完整哦，咱们先聊完摸底评估～"
                else:
                    # 使用 agent 处理
                    intent = detect_intent(user_input)

                    if intent == "D":
                        reply = check_injury(user_input)
                    elif intent == "C":
                        reply = answer_knowledge(user_input)
                    else:
                        result = chat(user_input, st.session_state.messages[:-1], st.session_state.runner_info)
                        reply = result["reply"]
                        st.session_state.runner_info = result["runner_info"]

                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})

        st.rerun()

else:

    if st.session_state.plan_text:
        with st.container(height=600):
            st.markdown(st.session_state.plan_text)
    else:
        st.info("👈 完成摸底评估后，回复「生成计划」即可查看你的专属训练计划")

        # 展示进度条示意
        ri = st.session_state.runner_info
        steps = []
        if not ri.get("goal_distance_km"):
            steps.append("❌ 设定目标")
        else:
            steps.append("✅ 设定目标")
        if not ri.get("fitness_level"):
            steps.append("❌ 评估体能")
        else:
            steps.append("✅ 评估体能")
        if not ri.get("age"):
            steps.append("❌ 身体信息")
        else:
            steps.append("✅ 身体信息")

        for step in steps:
            st.write(step)

        if len([s for s in steps if s.startswith("✅")]) == 3:
            st.success("全部信息已收集！回复「生成计划」即可")

print("Streamlit app loaded — run: streamlit run src/ui/app.py")
