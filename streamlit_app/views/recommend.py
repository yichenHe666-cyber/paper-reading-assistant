import streamlit as st
from streamlit_app.utils.api_client import post
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state

st.markdown(f"""
<div class="main-header">
    <h1>{icon('bullseye', size='lg')} 智能推荐</h1>
    <p>基于你的阅读历史和难度偏好，推荐下一篇论文</p>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.subheader("⬆️ 难度升级推荐")
    st.caption("读够了简单论文后，系统会推荐更高难度的论文")
    if st.button("⬆️ 推荐下一篇（难度升级）", use_container_width=True, type="primary"):
        with st.spinner("分析阅读历史..."):
            result = post("/api/recommend/next", {})
        if result.get("title"):
            card(
                content=f"""
                <div style="font-size:1.15rem; font-weight:600; color:var(--color-text-primary); margin-bottom:0.4rem;">{result.get('title', '')}</div>
                <div style="font-size:0.85rem; color:var(--color-text-secondary);">
                    {icon('user', size='xs')} {result.get('authors', '')} | {icon('calendar', size='xs')} {result.get('year', '')} | {icon('signal', size='xs')} {result.get('difficulty', '')}
                </div>
                """,
                variant="default",
                padding="1.25rem",
            )
            st.info(f"{icon('lightbulb', size='sm')} {result.get('reason', '')}")
            if st.button("📖 开始精读这篇", key="start_rec", use_container_width=True):
                st.session_state.selected_paper_id = result["id"]
                st.session_state.generated = {}
                st.switch_page("views/reading_workbench.py")
        else:
            empty_state(title="暂无推荐", description=result.get("message", "暂无推荐"), icon_name="bullseye")

with col2:
    st.subheader("❓ 概念补充推荐")
    st.caption("基于你标记为没看懂的概念，推荐相关论文")
    if st.button("🔍 推荐补充论文", use_container_width=True):
        with st.spinner("分析概念缺口..."):
            result = post("/api/recommend/next", {"topic_id": ""})
        if isinstance(result, list):
            for r in result[:3]:
                card(
                    content=f"""
                    <div style="font-size:1.15rem; font-weight:600; color:var(--color-text-primary); margin-bottom:0.4rem;">{r.get('title', '')}</div>
                    <div style="font-size:0.85rem; color:var(--color-text-secondary);">{icon('signal', size='xs')} {r.get('difficulty', '')}</div>
                    """,
                    variant="default",
                    padding="1rem",
                )
        else:
            empty_state(title="暂无推荐", description="暂无基于概念的推荐", icon_name="search")

st.divider()
st.subheader("💡 推荐算法说明")
st.markdown(f"""
- **难度升级**：读 3 篇简单 → 推荐中等，读 5 篇中等 → 推荐困难
- **主题偏好**：分析你最常读的主题，优先推荐同主题论文
- **概念补充**：(计划中) 基于你笔记中标记为 ❓ 的概念推荐
""")
