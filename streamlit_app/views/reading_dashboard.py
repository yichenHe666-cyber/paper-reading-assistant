import streamlit as st
from streamlit_app.utils.api_client import get
from streamlit_app.components.icon import icon
from streamlit_app.components.metric_card import metric_row
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state
import pandas as pd

st.markdown(f"""
<div class="main-header">
    <h1>{icon('chart_line', size='lg')} 阅读仪表盘</h1>
    <p>实时追踪你的论文阅读进度、时长与主题分布</p>
</div>
""", unsafe_allow_html=True)

try:
    stats = get("/api/system/reading-stats")
except Exception:
    stats = {}
    st.warning("无法连接后端获取阅读统计数据")

metric_row([
    {"value": str(stats.get('month_read_count', 0)), "label": "本月已读篇数", "icon_name": "book_open"},
    {"value": f"{stats.get('month_reading_hours', 0.0):.1f}", "label": "本月阅读时长(小时)", "icon_name": "clock"},
    {"value": str(stats.get('total_completed', 0)), "label": "总完成篇数", "icon_name": "check"},
    {"value": f"{stats.get('total_reading_hours', 0.0):.1f}", "label": "总阅读时长(小时)", "icon_name": "chart_line"},
])

st.divider()

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("🥧 主题分布")
    topic_dist = stats.get("topic_distribution", {})
    if topic_dist:
        df = pd.DataFrame({"主题": list(topic_dist.keys()), "篇数": list(topic_dist.values())})
        st.bar_chart(df.set_index("主题"), use_container_width=True)
    else:
        empty_state(title="暂无数据", description="暂无主题分布数据", icon_name="chart_pie")

with col_right:
    st.subheader("📖 阅读状态统计")
    read_status = stats.get("read_status_counts", {})
    c_a, c_b = st.columns(2)
    with c_a:
        card(content=f"""
        <div style="text-align:center;">
            <div style="font-size:2rem; font-weight:700; color:var(--color-primary);">{read_status.get('未读', 0)}</div>
            <div style="font-size:0.875rem; color:var(--color-text-secondary);">{icon('bookmark', size='sm')} 未读</div>
        </div>
        """, variant="default", padding="1rem")
        card(content=f"""
        <div style="text-align:center;">
            <div style="font-size:2rem; font-weight:700; color:var(--color-info);">{read_status.get('精读中', 0)}</div>
            <div style="font-size:0.875rem; color:var(--color-text-secondary);">{icon('book_open', size='sm')} 精读中</div>
        </div>
        """, variant="default", padding="1rem")
    with c_b:
        card(content=f"""
        <div style="text-align:center;">
            <div style="font-size:2rem; font-weight:700; color:var(--color-success);">{read_status.get('已读', 0)}</div>
            <div style="font-size:0.875rem; color:var(--color-text-secondary);">{icon('check', size='sm')} 已读</div>
        </div>
        """, variant="default", padding="1rem")
        card(content=f"""
        <div style="text-align:center;">
            <div style="font-size:2rem; font-weight:700; color:var(--color-warning);">{read_status.get('重读', 0)}</div>
            <div style="font-size:0.875rem; color:var(--color-text-secondary);">{icon('refresh', size='sm')} 重读</div>
        </div>
        """, variant="default", padding="1rem")

st.divider()

st.subheader("💡 阅读习惯小贴士")
tips = [
    ("bookmark", "每天精读 30 分钟，比周末突击 3 小时更有效"),
    ("brain", "读完后写 3 句总结，记忆留存率提升 70%"),
    ("refresh", "定期回顾已读论文的笔记，建立知识网络"),
    ("pen_to_square", "将核心概念写成卡片，便于日后检索与复习"),
]
cols = st.columns(4)
for i, (tip_icon, tip_text) in enumerate(tips):
    with cols[i]:
        card(content=f"""
        <div style="text-align:center; padding:1rem;">
            <div style="font-size:1.5rem; color:var(--color-primary); margin-bottom:0.5rem;">{icon(tip_icon, size='lg')}</div>
            <p style="font-size:0.85rem; color:var(--color-text-secondary); margin:0;">{tip_text}</p>
        </div>
        """, variant="default", padding="1rem")
