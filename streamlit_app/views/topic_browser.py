import streamlit as st
from streamlit_app.utils.api_client import get, patch
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.badge import badge
from streamlit_app.components.empty_state import empty_state

# ── Header ─────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1><i class="fa-solid fa-folder-open"></i> 主题浏览</h1>
    <p>按主题分类浏览 Papers We Love 经典论文</p>
</div>
""", unsafe_allow_html=True)

try:
    topics = get("/api/topics")
except Exception:
    topics = []
    st.warning("无法连接后端服务，请确认 FastAPI 已启动")

if not topics:
    empty_state(
        title="暂无数据",
        description="还没有论文数据，请返回首页点击「同步论文库」",
        icon_name="inbox",
        action_label="返回首页",
        action_key="go_home",
    )
    if st.button("返回首页", key="go_home_btn", use_container_width=True):
        st.switch_page("views/home_content.py")
else:
    topic_map = {f"{t.get('name_cn', t['name'])}": t["id"] for t in topics}
    topic_options = ["全部主题"] + list(topic_map.keys())

    if st.session_state.get("_navigate_to_topic"):
        target_id = st.session_state["_navigate_to_topic"]
        for label, tid in topic_map.items():
            if tid == target_id:
                st.session_state.topic_select = label
                break
        st.session_state["_navigate_to_topic"] = None

    col1, col2 = st.columns([3, 1])
    with col1:
        selected_label = st.selectbox("选择主题", topic_options, key="topic_select")
    with col2:
        if st.button("🔄 刷新", use_container_width=True):
            st.rerun()

    if selected_label == "全部主题":
        st.session_state.selected_topic = None
        st.subheader("📂 所有主题")
        rows = [topics[i:i+3] for i in range(0, len(topics), 3)]
        for row in rows:
            cols = st.columns(3)
            for i, topic in enumerate(row):
                with cols[i]:
                    fa_icon = topic.get('fa_icon', 'file-lines')
                    card(
                        content=f"""
                        <div style="text-align:center;">
                            <div class="topic-icon-duotone" style="font-size:2.5rem; margin-bottom:0.5rem;">
                                <i class="fa-solid fa-{fa_icon}"></i>
                            </div>
                            <div style="font-weight:600; color:var(--color-text-primary); font-size:1rem;">{topic.get('name_cn', topic.get('name', ''))}</div>
                            <div style="color:var(--color-primary); font-weight:600; font-size:0.85rem;">{topic.get('paper_count', 0)} 篇论文</div>
                        </div>
                        """,
                        variant="default",
                        padding="1.5rem",
                    )
                    if st.button("浏览论文", key=f"browse_{topic['id']}", use_container_width=True):
                        st.session_state.selected_topic = topic["id"]
                        st.session_state["_navigate_to_topic"] = topic["id"]
                        st.rerun()
    else:
        topic_id = topic_map.get(selected_label, selected_label)
        st.session_state.selected_topic = topic_id

        topic_data = None
        try:
            topic_data = get(f"/api/topics/{topic_id}")
        except Exception:
            st.error("获取主题数据失败")

        if topic_data:
            if "error" in topic_data:
                st.error(f"API返回错误: {topic_data['error']}")
            else:
                papers = topic_data.get("papers", [])
                fa_icon_topic = topic_data.get('fa_icon', 'file-lines')
                st.subheader(f"<i class=\"fa-solid fa-{fa_icon_topic}\"></i> {topic_data.get('name_cn', topic_data.get('name', ''))} — {len(papers)} 篇", unsafe_allow_html=True)

                status_filter = st.multiselect("状态筛选", ["未读", "精读中", "已读", "重读"], default=[], key="status_filter")
                if status_filter:
                    papers = [p for p in papers if p.get("read_status") in status_filter]

                if not papers:
                    empty_state(
                        title="该主题下没有论文",
                        description="该主题下暂时没有论文，请尝试其他主题或同步论文库。",
                        icon_name="inbox",
                    )
                else:
                    STATUS_CONFIG = {
                        "未读": ("未读", "default"),
                        "精读中": ("精读中", "info"),
                        "已读": ("已读", "success"),
                        "重读": ("重读", "warning"),
                    }
                    DIFF_CLASS = {"简单": "diff-simple", "中等": "diff-medium", "困难": "diff-hard", "硬核": "diff-extreme"}

                    for paper in papers:
                        authors_str = paper.get("authors", "")
                        try:
                            import json
                            authors_list = json.loads(authors_str) if isinstance(authors_str, str) else authors_str
                            authors_display = ", ".join(authors_list[:3])
                        except Exception:
                            authors_display = str(authors_str)[:50] if authors_str else "Unknown"

                        status_cfg = STATUS_CONFIG.get(paper.get("read_status"), ("未知", "default"))
                        diff = paper.get("difficulty", "中等")
                        diff_class = DIFF_CLASS.get(diff, "diff-medium")
                        synced_badge = f'<span class="ui-badge ui-badge-success">{icon("check", size="xs")} Obsidian</span>' if paper.get("obsidian_synced") else ""

                        card(
                            content=f"""
                            <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:8px;">
                                <div style="flex:1; min-width:200px;">
                                    <div style="font-size:1.15rem; font-weight:600; color:var(--color-text-primary); margin-bottom:0.4rem;">{paper.get('title', 'Untitled')}</div>
                                    <div style="font-size:0.85rem; color:var(--color-text-secondary); display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                                        <span>{icon('user', size='xs')} {authors_display}</span>
                                        <span>|</span>
                                        <span>{icon('calendar', size='xs')} {paper.get('year', 'N/A')}</span>
                                        <span>|</span>
                                        <span class="{diff_class}">{icon('signal', size='xs')} {diff}</span>
                                        <span>|</span>
                                        <span class="ui-badge ui-badge-{status_cfg[1]}">{status_cfg[0]}</span>
                                        {synced_badge}
                                    </div>
                                </div>
                            </div>
                            """,
                            variant="default",
                            padding="1.25rem",
                        )

                        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                        with col2:
                            if paper.get("read_status") == "未读":
                                if st.button("📖 开始精读", key=f"start_{paper['id']}", use_container_width=True):
                                    st.session_state.selected_paper_id = paper["id"]
                                    st.session_state.generated = {}
                                    st.switch_page("views/reading_workbench.py")
                            elif paper.get("read_status") == "精读中":
                                if st.button("📖 继续精读", key=f"cont_{paper['id']}", use_container_width=True):
                                    st.session_state.selected_paper_id = paper["id"]
                                    st.switch_page("views/reading_workbench.py")
                        with col3:
                            if paper.get("read_status") == "未读":
                                if st.button("✅ 标记已读", key=f"mark_{paper['id']}", use_container_width=True):
                                    patch(f"/api/papers/{paper['id']}", {"read_status": "已读"})
                                    st.rerun()
                        with col4:
                            if paper.get("pdf_url"):
                                st.markdown(f"""
                                <a href="{paper['pdf_url']}" target="_blank" style="text-decoration:none;">
                                    <button style="width:100%;padding:0.4rem 0.8rem;border-radius:10px;border:1.5px solid var(--color-primary);background:transparent;cursor:pointer;color:var(--color-primary);font-weight:600;transition:all 0.2s;">
                                        {icon('file_pdf', size='sm')} PDF
                                    </button>
                                </a>
                                """, unsafe_allow_html=True)

                        st.markdown("<hr style='margin:0.5rem 0;opacity:0.3;'>", unsafe_allow_html=True)
