import streamlit as st
from streamlit_app.utils.api_client import get
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state
import time

st.markdown(f"""
<div class="main-header">
    <h1>{icon('clock_rotate_left', size='lg')} 操作日志</h1>
    <p>查看系统各组件操作记录，支持按级别和组件筛选</p>
</div>
""", unsafe_allow_html=True)

LEVEL_CONFIG = {
    "INFO": ("info", "#3b82f6"),
    "WARNING": ("warning", "#f59e0b"),
    "ERROR": ("danger", "#ef4444"),
}

COMPONENT_OPTIONS = ["paper_fetch", "llm_call", "obsidian_write", "system", "reading"]
LEVEL_OPTIONS = ["INFO", "WARNING", "ERROR"]

col_filter1, col_filter2, col_filter3 = st.columns([2, 2, 1])
with col_filter1:
    selected_levels = st.multiselect("日志级别", LEVEL_OPTIONS, default=["INFO", "WARNING", "ERROR"])
with col_filter2:
    selected_components = st.multiselect("组件", COMPONENT_OPTIONS, default=[])
with col_filter3:
    st.markdown("<br>", unsafe_allow_html=True)
    refresh = st.button("🔄 刷新", use_container_width=True)

limit = 50

def fetch_logs():
    level_param = ",".join(selected_levels) if selected_levels else ""
    comp_param = ",".join(selected_components) if selected_components else ""
    params = []
    if comp_param:
        params.append(f"component={comp_param}")
    if level_param:
        params.append(f"level={level_param}")
    params.append(f"limit={limit}")
    query = "&".join(params)
    try:
        return get(f"/api/system/logs?{query}")
    except Exception:
        return []

logs = fetch_logs()

st.divider()

if not logs:
    empty_state(title="暂无日志", description="暂无日志记录", icon_name="inbox")
else:
    st.caption(f"共 {len(logs)} 条日志记录")
    for log in logs:
        level = log.get("level", "INFO")
        cfg = LEVEL_CONFIG.get(level, ("default", "#64748b"))
        color = cfg[1]
        created_at = str(log.get("created_at", ""))[:19]
        component = log.get("component", "-")
        message = log.get("message", "")
        card(
            content=f"""
            <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                <span class="ui-badge ui-badge-{cfg[0]}" style="background:{color}; color:#fff;">{level}</span>
                <span style="color:var(--color-text-muted); font-size:0.8rem;">{created_at}</span>
                <span style="color:var(--color-text-secondary); font-size:0.8rem;">{icon('box', size='xs')} {component}</span>
            </div>
            <div style="margin-top:0.3rem; color:var(--color-text-primary); font-size:0.85rem;">{message}</div>
            """,
            variant="default",
            padding="0.6rem 1rem",
            margin="0 0 0.5rem 0",
            custom_class="",
        )

if refresh:
    st.rerun()
