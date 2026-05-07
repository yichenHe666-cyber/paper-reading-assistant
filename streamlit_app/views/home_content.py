import streamlit as st
import html
import time

try:
    from streamlit_app.utils.api_client import get, post, health_check
except ImportError:

    def health_check() -> bool:
        return False

    def get(endpoint: str):
        raise RuntimeError("api_client module not available")

    def post(endpoint: str, data: dict = None):
        raise RuntimeError("api_client module not available")


from streamlit_app.components.icon import icon, icon_title, icon_caption
from streamlit_app.components.metric_card import metric_row
from streamlit_app.components.card import card, card_header

# ── Backend connectivity check ─────────────────────────────
_backend_ok = health_check()

# ── Hero Header ────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1><i class="fa-solid fa-book-open" style="color:#2dd4bf;"></i> 核动力科研牛马</h1>
    <p>从 Papers We Love 社区中发掘经典计算机科学论文，AI 辅助阅读，一键写入 Obsidian</p>
</div>
""", unsafe_allow_html=True)

if not _backend_ok:
    st.error("""
    ⚠️ **后端服务未启动**

    请先运行后端子服务，再刷新页面：

    1. 打开新终端
    2. 运行：`python start_app.py`

    或手动启动后端：
    ```
    uvicorn app.main:app --host 127.0.0.1 --port 8000
    ```
    """)
    st.stop()

# ── Metrics ────────────────────────────────────────────────
try:
    stats = get("/api/system/stats")
except Exception:
    stats = {"total_papers": 0, "unread": 0, "reading": 0, "read": 0, "total_topics": 0, "synced_to_obsidian": 0}

metric_row([
    {"value": str(stats.get("total_papers", 0)), "label": "经典论文", "icon_name": "file_lines"},
    {"value": str(stats.get("unread", 0)), "label": "待精读", "icon_name": "bookmark"},
    {"value": str(stats.get("read", 0)), "label": "已读完", "icon_name": "check"},
    {"value": str(stats.get("synced_to_obsidian", 0)), "label": "已写入 Obsidian", "icon_name": "pen_to_square"},
])

st.divider()

# ── Quick Start Cards ──────────────────────────────────────
st.markdown(icon_title("三步开始", "rocket", "sm", "h3"), unsafe_allow_html=True)
col_a, col_b, col_c = st.columns(3)

with col_a:
    card(
        content=f"""
        <div style="text-align:center;">
            <div style="font-size:3rem; margin-bottom:0.5rem; color:#2dd4bf;">
                {icon('download', size='2xl')}
            </div>
            <div style="font-size:1.2rem; font-weight:700; margin-bottom:0.5rem; color:var(--color-text-primary);">同步论文库</div>
            <p style="font-size:0.85rem; color:var(--color-text-primary); margin:0;">从 GitHub 拉取<br>Papers We Love 经典论文</p>
        </div>
        """,
        variant="gradient",
        padding="2rem 1.5rem",
        hover=False,
    )
    if st.button("立即同步", key="sync_home_btn_v4", use_container_width=True):
        force_sync = st.session_state.get("_force_sync", False)
        with st.spinner("正在从 GitHub 拉取论文..."):
            result = post(f"/api/topics/fetch?force={str(force_sync).lower()}")
        if result.get("status") == "ok":
            st.success(f"同步完成 — 新增 {result.get('new', 0)} 篇，共 {result.get('total', 0)} 篇")
            empty = result.get("empty_topics", 0)
            if empty > 0:
                st.info(f"仍有 {empty} 个主题暂无论文，可使用「强制重新同步」尝试收录")
            st.session_state["_force_sync"] = False
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"同步失败: {result.get('message', '未知错误')}")

with col_b:
    card(
        content=f"""
        <div style="text-align:center;">
            <div style="font-size:3rem; margin-bottom:0.5rem; color:#2dd4bf;">
                {icon('folder_open', size='2xl')}
            </div>
            <div style="font-size:1.2rem; font-weight:700; margin-bottom:0.5rem; color:var(--color-text-primary);">选择论文</div>
            <p style="font-size:0.85rem; color:var(--color-text-secondary); margin:0;">按主题浏览<br>找到你感兴趣的经典论文</p>
        </div>
        """,
        variant="gradient",
        padding="2rem 1.5rem",
        hover=False,
    )
    if st.button("浏览主题", key="browse_home", use_container_width=True):
        st.switch_page("views/topic_browser.py")

with col_c:
    card(
        content=f"""
        <div style="text-align:center;">
            <div style="font-size:3rem; margin-bottom:0.5rem; color:#2dd4bf;">
                {icon('sparkles', size='2xl')}
            </div>
            <div style="font-size:1.2rem; font-weight:700; margin-bottom:0.5rem; color:var(--color-text-primary);">AI 精读</div>
            <p style="font-size:0.85rem; color:var(--color-text-secondary); margin:0;">一键生成阅读导航<br>笔记草稿 · 概念卡片</p>
        </div>
        """,
        variant="gradient",
        padding="2rem 1.5rem",
        hover=False,
    )
    if st.button("开始精读", key="reading_home", use_container_width=True):
        st.switch_page("views/reading_workbench.py")

st.divider()

# ── Topic Overview ─────────────────────────────────────────
st.markdown(icon_title("主题概览", "list", "sm", "h3"), unsafe_allow_html=True)
try:
    topics = get("/api/topics")
except Exception:
    topics = []

if topics:
    total_papers_in_topics = sum(t.get('paper_count', 0) for t in topics)
    topics_with_papers = [t for t in topics if t.get('paper_count', 0) > 0]
    topics_without_papers = [t for t in topics if t.get('paper_count', 0) == 0]

    st.markdown(f"<div style='color:var(--color-text-secondary);font-size:0.9rem;margin-bottom:0.5rem;'>共 <b>{len(topics)}</b> 个主题，<b>{total_papers_in_topics}</b> 篇论文已归类</div>", unsafe_allow_html=True)

    rows = [topics_with_papers[i:i+4] for i in range(0, len(topics_with_papers), 4)]
    for row in rows:
        cols = st.columns(len(row))
        for i, topic in enumerate(row):
            with cols[i]:
                fa_icon = topic.get('fa_icon', 'file-lines')
                card(
                    content=f"""
                    <div style="text-align:center;">
                        <div class="topic-icon-duotone" style="font-size:2rem; margin-bottom:0.5rem;">
                            <i class="fa-solid fa-{html.escape(fa_icon)}"></i>
                        </div>
                        <div style="font-weight:600; color:var(--color-text-primary); font-size:1rem;">{html.escape(topic.get('name_cn', topic.get('name', '')))}</div>
                        <div style="color:var(--color-primary); font-weight:600; font-size:0.85rem;">{html.escape(str(topic.get('paper_count', 0)))} 篇论文</div>
                    </div>
                    """,
                    variant="gradient",
                    padding="1.5rem",
                    margin="0 0 0.5rem 0",
                    hover=True,
                )
                if st.button("查看", key=f"topic_btn_{topic['id']}", use_container_width=True):
                    st.session_state.selected_topic = topic["id"]
                    st.session_state["_navigate_to_topic"] = topic["id"]
                    st.session_state.selected_paper_id = None
                    st.session_state.generated = {}
                    st.switch_page("views/topic_browser.py")

    if topics_without_papers:
        with st.expander(f"📋 待收录论文的主题 ({len(topics_without_papers)} 个)", expanded=False):
            cols_per_row = 4
            empty_rows = [topics_without_papers[i:i+cols_per_row] for i in range(0, len(topics_without_papers), cols_per_row)]
            for row in empty_rows:
                ecols = st.columns(len(row))
                for i, topic in enumerate(row):
                    with ecols[i]:
                        fa_icon_empty = topic.get('fa_icon', 'file-lines')
                        st.markdown(f"<div style='text-align:center;padding:0.5rem;opacity:0.6;'><div class='topic-icon-duotone' style='font-size:1.5rem;'><i class='fa-solid fa-{html.escape(fa_icon_empty)}'></i></div><div style='font-size:0.85rem;'>{html.escape(topic.get('name_cn', topic.get('name', '')))}</div><div style='font-size:0.75rem;color:var(--color-text-secondary);'>暂无论文</div></div>", unsafe_allow_html=True)
            if st.button("🔄 强制重新同步所有主题", key="force_resync_btn", use_container_width=True):
                st.session_state["_force_sync"] = True
                st.rerun()
else:
    from streamlit_app.components.empty_state import empty_state
    empty_state(
        title="暂无论文数据",
        description="还没有论文数据，请先点击「同步论文库」从 GitHub 拉取论文列表。",
        icon_name="inbox",
        action_label="立即同步",
        action_key="sync_empty",
    )
