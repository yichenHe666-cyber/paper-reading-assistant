import streamlit as st
from streamlit_app.utils.api_client import get, post
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state

st.markdown(f"""
<div class="main-header">
    <h1>{icon('clock_rotate_left', size='lg')} 版本回溯</h1>
    <p>笔记历史版本管理</p>
</div>
""", unsafe_allow_html=True)

try:
    papers_resp = get("/api/papers?page_size=500")
except Exception:
    papers_resp = {}

papers = papers_resp.get("papers", []) if isinstance(papers_resp, dict) else []

if not papers:
    empty_state(
        title="暂无论文数据",
        description="请先在首页同步论文库。",
        icon_name="inbox",
        action_label="返回首页",
        action_key="go_home_vh",
    )
    if st.button("返回首页", key="go_home_vh_btn", use_container_width=True):
        st.switch_page("views/home_content.py")
else:
    paper_options = {f"{p.get('title', 'Untitled')[:60]} ({p.get('id','')})": p["id"] for p in papers if p.get("id")}
    selected_label = st.selectbox("选择一篇论文查看其版本历史", list(paper_options.keys()))

    st.divider()

    if selected_label:
        paper_id = paper_options[selected_label]
        st.subheader("📋 版本历史")

        try:
            snapshots = get(f"/api/obsidian/snapshots/{paper_id}")
        except Exception:
            snapshots = {"snapshots": []}
            st.warning("无法获取快照数据")

        items = snapshots.get("snapshots", [])
        if not items:
            empty_state(
                title="暂无版本快照",
                description="该论文还没有版本快照。写入过 Obsidian 后会自动保存旧版本。",
                icon_name="inbox",
            )
        else:
            for s in items:
                col1, col2 = st.columns([4, 1])
                with col1:
                    card(
                        content=f"""
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                            <div>
                                <b>版本 #{s.get('version', '?')}</b>
                                <span style="color:var(--color-text-muted); font-size:0.8rem; margin-left:1rem;">{s.get('created_at', '')}</span>
                            </div>
                            <div style="color:var(--color-text-secondary); font-size:0.85rem;">{s.get('obsidian_path', '')}</div>
                        </div>
                        """,
                        variant="default",
                        padding="1rem",
                    )
                with col2:
                    if st.button("回滚到此版本", key=f"rollback_{s['id']}", use_container_width=True):
                        try:
                            result = post("/api/obsidian/rollback", {"snapshot_id": s["id"], "paper_id": paper_id})
                        except Exception as e:
                            result = {"error": str(e)}
                        if result.get("status") == "ok":
                            st.success("回滚成功")
                            st.rerun()
                        else:
                            st.error(result.get("error", "回滚失败"))
