import streamlit as st
from streamlit_app.utils.api_client import get
from streamlit_app.components.icon import icon
from streamlit_app.components.metric_card import metric_row
from streamlit_app.components.empty_state import empty_state
import pandas as pd

st.markdown(f"""
<div class="main-header">
    <h1>{icon('chart_pie', size='lg')} 阅读统计</h1>
    <p>追踪你的经典论文阅读进度</p>
</div>
""", unsafe_allow_html=True)

try:
    stats = get("/api/system/stats")
except Exception:
    stats = {}
    st.warning("无法连接后端")

metric_row([
    {"value": str(stats.get('total_papers', 0)), "label": "论文总数", "icon_name": "file_lines"},
    {"value": str(stats.get('unread', 0)), "label": "未读", "icon_name": "bookmark"},
    {"value": str(stats.get('reading', 0)), "label": "精读中", "icon_name": "book_open"},
    {"value": str(stats.get('read', 0)), "label": "已读", "icon_name": "check"},
    {"value": str(stats.get('reread', 0)), "label": "重读", "icon_name": "refresh"},
])

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📊 阅读状态分布")
    status_data = {
        "状态": ["未读", "精读中", "已读", "重读"],
        "数量": [
            stats.get("unread", 0),
            stats.get("reading", 0),
            stats.get("read", 0),
            stats.get("reread", 0),
        ],
    }
    df = pd.DataFrame(status_data)
    st.bar_chart(df.set_index("状态"), use_container_width=True)

with col_right:
    st.subheader("📤 Obsidian 同步")
    obsidian_data = {
        "类别": ["已同步", "未同步"],
        "数量": [
            stats.get("synced_to_obsidian", 0),
            max(0, stats.get("total_papers", 0) - stats.get("synced_to_obsidian", 0)),
        ],
    }
    df2 = pd.DataFrame(obsidian_data)
    st.bar_chart(df2.set_index("类别"), use_container_width=True, color="#34d399")

try:
    cost = get("/api/system/llm-cost")
except Exception:
    cost = {}

if cost:
    st.divider()
    st.subheader("🧾 LLM 花费")

    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("今日花费", f"${cost.get('today_cost_usd', 0):.4f}")
    with col_b:
        st.metric("累计花费", f"${cost.get('total_cost_usd', 0):.4f}")

    try:
        cost_detail = get("/api/system/llm-cost/detail?limit=20")
        if cost_detail:
            with st.expander("📋 花费明细"):
                st.dataframe(
                    [{"类型": c["call_type"], "模型": c["model"], "费用": f"${c['cost_usd']:.4f}",
                      "Tokens": c["total_tokens"], "时间": str(c["created_at"])[:19]} for c in cost_detail],
                    use_container_width=True, hide_index=True
                )
    except Exception:
        pass

st.divider()
st.subheader(f"📂 共 {stats.get('total_topics', 0)} 个主题")
st.caption("💡 如果你看到这里都还是 0，记得回首页先「同步论文库」哦~")
