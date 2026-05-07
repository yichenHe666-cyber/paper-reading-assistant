import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit_app.utils.api_client import get, post
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state
from streamlit_app.components.badge import badge

st.markdown("""
<div class="main-header">
    <h1><i class="fa-solid fa-microscope"></i> AI 研究助手</h1>
    <p>基于 GPT Researcher 的自主深度研究引擎，为你的论文阅读提供相关研究综述和文献检索</p>
</div>
""", unsafe_allow_html=True)

tab_research, tab_history, tab_guide = st.tabs([
    "发起研究",
    "研究历史",
    "使用指引",
])

with tab_guide:
    st.markdown("### 🎯 如何使用 AI 研究助手")
    steps = [
        ("🔍", "输入研究问题", "描述你想深入了解的研究方向，例如\"Transformer注意力机制的最新改进\""),
        ("🔎", "选择报告类型", "快速摘要(约2分钟)或深度分析(约5分钟)"),
        ("🔗", "可选：关联论文", "将研究结果关联到当前阅读的论文，方便后续查阅"),
        ("⏱️", "等待研究完成", "AI 将自动搜索、分析多个来源，生成带引用的研究报告"),
        ("👁️", "查看与关联", "在\"研究历史\"中查看结果，或从阅读工作台关联已有研究"),
    ]
    for step_icon, title, desc in steps:
        card(
            content=f"""
            <div style="display:flex; align-items:flex-start; gap:12px;">
                <div style="min-width:32px; height:32px; border-radius:50%; background:linear-gradient(135deg, var(--color-primary), var(--color-secondary)); color:#0B1120; display:flex; align-items:center; justify-content:center; font-weight:700; font-size:0.85rem;">
                    {step_icon}
                </div>
                <div>
                    <div style="font-weight:600; color:var(--color-text-primary);">{title}</div>
                    <div style="font-size:0.875rem; color:var(--color-text-secondary);">{desc}</div>
                </div>
            </div>
            """,
            variant="default",
            padding="1rem 1.5rem",
            margin="0 0 0.8rem 0",
        )

    st.markdown("#### 💡 研究技巧")
    tips = [
        "**具体化问题**：越具体的问题，生成的研究报告越有针对性",
        "**使用学术语言**：如\"对比分析\"、\"系统性综述\"等关键词能提升报告质量",
        "**关联论文**：在阅读论文时发起相关研究，可获得更丰富的背景资料",
        "**选择深度报告**：需要全面了解某个领域时，选择\"深度分析\"模式",
    ]
    for tip in tips:
        st.markdown(f"- {tip}")

with tab_research:
    with st.form("research_form"):
        query = st.text_area(
            "研究问题",
            placeholder="例如：Transformer注意力机制的最新改进有哪些？对比分析各种变体的优劣",
            height=100,
        )

        col1, col2 = st.columns(2)
        with col1:
            report_type = st.selectbox(
                "报告类型",
                options=[
                    ("快速摘要 (~2分钟)", "research_report"),
                    ("深度分析 (~5分钟)", "detailed_report"),
                    ("资源报告", "resource_report"),
                    ("深度研究", "deep"),
                ],
                format_func=lambda x: x[0],
                index=0,
            )
        with col2:
            tone = st.selectbox(
                "写作风格",
                options=[
                    ("客观", "Objective"),
                    ("学术", "Formal"),
                    ("分析", "Analytical"),
                    ("信息", "Informative"),
                    ("批判", "Critical"),
                    ("比较", "Comparative"),
                ],
                format_func=lambda x: x[0],
                index=0,
            )

        report_source = st.selectbox(
            "信息来源",
            options=[
                ("网络搜索", "web"),
                ("本地文档", "local"),
                ("混合", "hybrid"),
            ],
            format_func=lambda x: x[0],
            index=0,
        )

        paper_id = st.text_input(
            "关联论文 ID（可选）",
            value=st.session_state.get("selected_paper_id", ""),
            placeholder="留空则不关联特定论文",
        )

        domains_str = st.text_input(
            "限定搜索域名（可选，逗号分隔）",
            placeholder="例如：arxiv.org, scholar.google.com",
        )

        submitted = st.form_submit_button("🚀 开始研究", use_container_width=True)

    if submitted:
        if not query.strip():
            st.error("请输入研究问题")
        else:
            query_domains = [d.strip() for d in domains_str.split(",") if d.strip()] if domains_str else None
            req_data = {
                "query": query.strip(),
                "report_type": report_type[1] if isinstance(report_type, tuple) else report_type,
                "report_source": report_source[1] if isinstance(report_source, tuple) else report_source,
                "tone": tone[1] if isinstance(tone, tuple) else tone,
                "query_domains": query_domains,
                "paper_id": paper_id.strip() if paper_id and paper_id.strip() else None,
            }

            with st.spinner("⏳ 正在执行深度研究，这可能需要几分钟..."):
                result = post("/api/research/sync", req_data)

            if "error" in result:
                st.error(f"研究失败：{result['error']}")
            else:
                st.session_state["last_research_result"] = result
                st.success("研究完成！")
                st.rerun()

    if "last_research_result" in st.session_state:
        result = st.session_state["last_research_result"]
        st.markdown("---")
        st.markdown("### 📄 最新研究结果")

        col_a, col_b = st.columns([3, 1])
        with col_b:
            st.metric("研究成本", f"${result.get('research_costs', 0):.4f}")
            if result.get("source_urls"):
                st.metric("参考来源数", len(result["source_urls"]))
            if result.get("retriever_used"):
                st.metric("搜索引擎", result["retriever_used"])

        with col_a:
            st.markdown(f"**研究问题：** {result.get('query', '')}")

        quality = result.get("quality_metrics", {})
        if quality:
            q_col1, q_col2, q_col3 = st.columns(3)
            with q_col1:
                st.metric("来源质量占比", f"{quality.get('high_quality_ratio', 0):.0%}")
            with q_col2:
                st.metric("平均新鲜度", f"{quality.get('avg_freshness_days', 0):.0f}天")
            with q_col3:
                st.metric("覆盖度", f"{quality.get('coverage_score', 0):.0%}")
            if quality.get("warning"):
                st.warning(quality["warning"])

        fallback_log = result.get("search_fallback_log") or result.get("fallback_log", [])
        if fallback_log:
            with st.expander("🔄 搜索引擎降级日志"):
                for entry in fallback_log:
                    status_icon = {"skipped": "⏭️", "empty": "📭", "error": "❌", "exhausted": "💀"}.get(entry.get("status", ""), "🔍")
                    st.markdown(f"{status_icon} **{entry.get('retriever', '?')}** — {entry.get('status', '?')}: {entry.get('reason', '')}")

        if result.get("report_content"):
            with st.expander("📝 研究报告", expanded=True):
                st.markdown(result["report_content"])

        if result.get("source_urls"):
            with st.expander("🔗 参考来源"):
                for url in result["source_urls"]:
                    st.markdown(f"- [{url}]({url})")

with tab_history:
    filter_paper = st.text_input("按论文 ID 筛选", placeholder="输入论文 ID 或留空查看全部")

    try:
        params = {}
        if filter_paper.strip():
            params["paper_id"] = filter_paper.strip()
        data = get("/api/research?" + "&".join(f"{k}={v}" for k, v in params.items()))
        reports = data.get("reports", [])
        total = data.get("total", 0)
    except Exception:
        reports = []
        total = 0

    st.caption(f"共 {total} 条研究记录")

    if not reports:
        empty_state(
            title="暂无研究记录",
            description="暂无研究记录。前往「发起研究」开始你的第一次 AI 研究！",
            icon_name="microscope",
            action_label="发起研究",
            action_key="go_research",
        )
    else:
        for r in reports:
            status = r.get("status", "unknown")
            status_cfg = {
                "pending": ("进行中", "warning"),
                "completed": ("已完成", "success"),
                "failed": ("失败", "danger"),
            }.get(status, ("未知", "default"))

            card(
                content=f"""
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                    <div>
                        <div style="font-weight:600; color:var(--color-text-primary);">{r.get('query', 'N/A')}</div>
                        <div style="font-size:0.8rem; color:var(--color-text-muted);">
                            <span class="ui-badge ui-badge-{status_cfg[1]}">{status_cfg[0]}</span>
                            {r.get('created_at', '')}
                        </div>
                    </div>
                </div>
                """,
                variant="default",
                padding="1rem 1.5rem",
            )

            if status == "completed" and r.get("report_content"):
                with st.expander(f"查看报告 — {r.get('query', '')[:30]}..."):
                    r_quality = r.get("quality_metrics", {})
                    if r_quality:
                        rq1, rq2, rq3 = st.columns(3)
                        with rq1:
                            st.metric("来源质量", f"{r_quality.get('high_quality_ratio', 0):.0%}")
                        with rq2:
                            st.metric("新鲜度", f"{r_quality.get('avg_freshness_days', 0):.0f}天")
                        with rq3:
                            st.metric("覆盖度", f"{r_quality.get('coverage_score', 0):.0%}")
                        if r_quality.get("warning"):
                            st.warning(r_quality["warning"])

                    if r.get("retriever_used"):
                        st.caption(f"🔍 搜索引擎: {r['retriever_used']}")

                    r_fallback = r.get("search_fallback_log", [])
                    if r_fallback:
                        with st.expander("降级日志"):
                            for entry in r_fallback:
                                status_icon = {"skipped": "⏭️", "empty": "📭", "error": "❌", "exhausted": "💀"}.get(entry.get("status", ""), "🔍")
                                st.markdown(f"{status_icon} **{entry.get('retriever', '?')}** — {entry.get('status', '?')}: {entry.get('reason', '')}")

                    st.markdown(r["report_content"])

                    if r.get("source_urls"):
                        st.markdown("**🔗 参考来源：**")
                        for url in r["source_urls"]:
                            st.markdown(f"- [{url}]({url})")

                    if r.get("paper_id"):
                        st.info(f"🔗 已关联论文：{r['paper_id']}")
                    else:
                        link_paper = st.text_input(
                            "关联到论文 ID",
                            key=f"link_{r['id']}",
                            placeholder="输入论文 ID",
                        )
                        if st.button("关联", key=f"link_btn_{r['id']}"):
                            if link_paper.strip():
                                res = post("/api/research/link", {
                                    "research_id": r["id"],
                                    "paper_id": link_paper.strip(),
                                })
                                if res.get("success"):
                                    st.success("关联成功！")
                                    st.rerun()
                                else:
                                    st.error("关联失败")

            col_del1, col_del2 = st.columns([5, 1])
            with col_del2:
                if st.button("🗑️ ", key=f"del_{r['id']}", help="删除此研究"):
                    try:
                        from streamlit_app.utils.api_client import get as _get
                        import requests
                        api_key = __import__("os").getenv("API_KEY", "")
                        headers = {"X-API-Key": api_key} if api_key else {}
                        resp = requests.delete(
                            f"http://127.0.0.1:8000/api/research/{r['id']}",
                            headers=headers,
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("已删除")
                            st.rerun()
                    except Exception as e:
                        st.error(f"删除失败: {e}")
