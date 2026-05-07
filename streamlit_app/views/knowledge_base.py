import streamlit as st
import requests
from streamlit_app.utils.api_client import get, post, delete, _headers, API_BASE
from streamlit_app.components.badge import badge, badge_group
from streamlit_app.components.empty_state import empty_state
from streamlit_app.components.metric_card import metric_row

FORMAT_ICONS = {
    "pdf": "📄", "md": "📝", "epub": "📚", "docx": "📃", "doc": "📃", "tex": "🔬",
}

PARSE_STATUS_MAP = {
    "pending": ("待解析", "warning"),
    "parsing": ("解析中", "info"),
    "completed": ("已完成", "success"),
    "failed": ("失败", "danger"),
}

WIKI_STATUS_MAP = {
    "none": ("未生成", "default"),
    "generating": ("生成中", "info"),
    "completed": ("已生成", "success"),
    "failed": ("失败", "danger"),
}

RELATION_STYLE = {
    "depends_on": {"dash": "solid", "color": "#94a3b8", "label": "依赖"},
    "analogous": {"dash": "dash", "color": "#38bdf8", "label": "类比"},
    "contradicts": {"dash": "solid", "color": "#f87171", "label": "矛盾"},
}

st.markdown("""
<div class="main-header">
    <h1>🗄️ 知识库</h1>
    <p>文档管理、知识图谱、智能查询与系统状态</p>
</div>
""", unsafe_allow_html=True)

tab_docs, tab_graph, tab_query, tab_status = st.tabs(["文档管理", "知识图谱", "知识查询", "系统状态"])

with tab_docs:
    with st.expander("📤 上传文档", expanded=False):
        uploaded_files = st.file_uploader(
            "选择文件",
            type=["pdf", "md", "epub", "docx", "doc", "tex"],
            accept_multiple_files=True,
            key="kb_upload_files",
        )
        col_cat, col_tags = st.columns(2)
        with col_cat:
            upload_category = st.text_input("分类", placeholder="如：论文、教材、笔记...", key="kb_upload_category")
        with col_tags:
            upload_tags = st.text_input("标签（逗号分隔）", placeholder="如：机器学习, 深度学习...", key="kb_upload_tags")

        if st.button("上传", type="primary", use_container_width=True, key="kb_upload_btn"):
            if not uploaded_files:
                st.warning("请选择至少一个文件")
            else:
                tags_list = [t.strip() for t in upload_tags.split(",") if t.strip()] if upload_tags else []
                success_count = 0
                fail_count = 0
                for f in uploaded_files:
                    try:
                        files = {"file": (f.name, f.getvalue(), "application/octet-stream")}
                        data = {}
                        if upload_category:
                            data["category"] = upload_category
                        if tags_list:
                            data["tags"] = ",".join(tags_list)
                        resp = requests.post(
                            f"{API_BASE}/api/knowledge/upload",
                            files=files,
                            data=data,
                            timeout=120,
                            headers=_headers(),
                        )
                        if resp.status_code == 200:
                            success_count += 1
                        else:
                            fail_count += 1
                            try:
                                detail = resp.json().get("detail", f"HTTP {resp.status_code}")
                            except Exception:
                                detail = f"HTTP {resp.status_code}"
                            st.error(f"上传 {f.name} 失败: {detail}")
                    except Exception as e:
                        fail_count += 1
                        st.error(f"上传 {f.name} 失败: {e}")
                if success_count > 0:
                    st.success(f"成功上传 {success_count} 个文件" + (f"，失败 {fail_count} 个" if fail_count > 0 else ""))
                    st.rerun()

    st.divider()

    col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1, 1, 2])
    with col_f1:
        filter_category = st.text_input("分类筛选", placeholder="输入分类...", key="kb_filter_category")
    with col_f2:
        filter_format = st.selectbox("格式筛选", ["全部", "pdf", "md", "epub", "docx", "doc", "tex"], key="kb_filter_format")
    with col_f3:
        filter_status = st.selectbox("状态筛选", ["全部", "pending", "parsing", "completed", "failed"],
                                     format_func=lambda x: "全部" if x == "全部" else PARSE_STATUS_MAP.get(x, (x, "default"))[0],
                                     key="kb_filter_status")
    with col_f4:
        filter_search = st.text_input("搜索", placeholder="输入文件名关键词...", key="kb_filter_search")

    params = {"limit": 200}
    if filter_category:
        params["category"] = filter_category
    if filter_format != "全部":
        params["format"] = filter_format
    if filter_status != "全部":
        params["parse_status"] = filter_status
    if filter_search:
        params["q"] = filter_search

    query_str = "&".join(f"{k}={v}" for k, v in params.items())
    try:
        docs_data = get(f"/api/knowledge/documents?{query_str}")
        documents = docs_data if isinstance(docs_data, list) else docs_data.get("documents", []) if isinstance(docs_data, dict) else []
    except Exception:
        documents = []
        st.warning("无法连接后端服务")

    if not documents:
        empty_state(title="暂无文档", description="上传第一个文档开始构建知识库", icon_name="database")
    else:
        st.caption(f"共 {len(documents)} 个文档")

        selected_ids = []
        col_batch1, col_batch2 = st.columns(2)
        with col_batch1:
            batch_delete = st.button("🗑️ 批量删除", use_container_width=True, key="kb_batch_delete")
        with col_batch2:
            batch_extract = st.button("⚙️ 批量提取", use_container_width=True, key="kb_batch_extract")

        for doc in documents:
            fmt = doc.get("format", "")
            fmt_icon = FORMAT_ICONS.get(fmt, "📎")
            parse_status = doc.get("parse_status", "pending")
            parse_label, parse_variant = PARSE_STATUS_MAP.get(parse_status, ("未知", "default"))
            wiki_status = doc.get("wiki_status", "none")
            wiki_label, wiki_variant = WIKI_STATUS_MAP.get(wiki_status, ("未知", "default"))

            header = f"{fmt_icon} {doc.get('file_name', '未知文件')}"
            with st.expander(header):
                col_info, col_badges = st.columns([3, 1])
                with col_info:
                    st.markdown(f"**分类：** {doc.get('category', '未分类')}")
                    tags = doc.get("tags", [])
                    if tags:
                        badge_group(tags if isinstance(tags, list) else tags.split(","), variant="default")
                with col_badges:
                    badge(parse_label, variant=parse_variant)
                    badge(wiki_label, variant=wiki_variant)

                if doc.get("created_at"):
                    st.caption(f"上传时间: {doc['created_at']}")

                col_a1, col_a2, col_a3 = st.columns(3)
                with col_a1:
                    if st.button("⚙️ 提取", key=f"extract_{doc.get('id', '')}", use_container_width=True):
                        try:
                            result = post(f"/api/knowledge/extract/{doc['id']}", {})
                            if isinstance(result, dict) and result.get("error"):
                                st.error(f"提取失败: {result['error']}")
                            else:
                                st.success("提取任务已启动")
                                st.rerun()
                        except Exception as e:
                            st.error(f"提取失败: {e}")
                with col_a2:
                    if st.button("📝 生成Wiki", key=f"wiki_{doc.get('id', '')}", use_container_width=True):
                        try:
                            result = post(f"/api/knowledge/wiki/{doc['id']}", {})
                            if isinstance(result, dict) and result.get("error"):
                                st.error(f"生成失败: {result['error']}")
                            else:
                                st.success("Wiki 生成任务已启动")
                                st.rerun()
                        except Exception as e:
                            st.error(f"生成失败: {e}")
                with col_a3:
                    if st.button("🗑️ 删除", key=f"del_doc_{doc.get('id', '')}", use_container_width=True):
                        st.session_state[f"confirm_del_doc_{doc.get('id', '')}"] = True

                if st.session_state.get(f"confirm_del_doc_{doc.get('id', '')}", False):
                    st.warning("确定要删除此文档吗？此操作不可恢复。")
                    col_y, col_n = st.columns(2)
                    with col_y:
                        if st.button("确认删除", key=f"yes_del_doc_{doc.get('id', '')}", type="primary", use_container_width=True):
                            try:
                                result = delete(f"/api/knowledge/documents/{doc['id']}")
                                if isinstance(result, dict) and result.get("error"):
                                    st.error(f"删除失败: {result['error']}")
                                else:
                                    st.success("文档已删除")
                                    st.session_state[f"confirm_del_doc_{doc.get('id', '')}"] = False
                                    st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")
                    with col_n:
                        if st.button("取消", key=f"no_del_doc_{doc.get('id', '')}", use_container_width=True):
                            st.session_state[f"confirm_del_doc_{doc.get('id', '')}"] = False
                            st.rerun()

with tab_graph:
    try:
        graph_data = get("/api/knowledge/graph")
    except Exception:
        graph_data = {}
        st.warning("无法获取知识图谱数据")

    nodes = graph_data.get("nodes", []) if isinstance(graph_data, dict) else []
    edges = graph_data.get("edges", []) if isinstance(graph_data, dict) else []

    if not nodes:
        empty_state(title="暂无知识图谱", description="上传并解析文档后，知识图谱将自动生成", icon_name="diagram_project")
    else:
        st.subheader(f"🕸️ 知识图谱 — {len(nodes)} 个节点, {len(edges)} 条边")

        col_gf1, col_gf2, col_gf3 = st.columns([1, 1, 2])
        with col_gf1:
            categories = list(set(n.get("category", "未分类") for n in nodes))
            selected_cats = st.multiselect("分类筛选", categories, default=categories, key="kb_graph_cat_filter")
        with col_gf2:
            relation_types = list(set(e.get("relation_type", "depends_on") for e in edges)) if edges else []
            selected_rels = st.multiselect("关系类型筛选", relation_types, default=relation_types, key="kb_graph_rel_filter")
        with col_gf3:
            graph_search = st.text_input("搜索概念", placeholder="输入概念名称高亮显示...", key="kb_graph_search")

        filtered_nodes = [n for n in nodes if n.get("category", "未分类") in selected_cats] if selected_cats else nodes
        filtered_names = {n.get("name") for n in filtered_nodes}
        filtered_edges = [e for e in edges if e.get("source") in filtered_names and e.get("target") in filtered_names and e.get("relation_type") in selected_rels] if selected_rels else [e for e in edges if e.get("source") in filtered_names and e.get("target") in filtered_names]

        col_chart, col_legend = st.columns([2, 1])

        with col_chart:
            try:
                import plotly.graph_objects as go

                node_names = [n.get("name", "") for n in filtered_nodes]
                name_to_idx = {n: i for i, n in enumerate(node_names)}

                cat_colors = {cat: f"hsl({hash(cat) % 360}, 60%, 60%)" for cat in set(n.get("category", "") for n in filtered_nodes)}
                node_colors = [cat_colors.get(n.get("category", ""), "#667eea") for n in filtered_nodes]

                degree_map = {}
                for e in filtered_edges:
                    degree_map[e.get("source", "")] = degree_map.get(e.get("source", ""), 0) + 1
                    degree_map[e.get("target", "")] = degree_map.get(e.get("target", ""), 0) + 1
                node_sizes = [max(12, degree_map.get(n.get("name", ""), 0) * 4 + 12) for n in filtered_nodes]

                if graph_search:
                    node_colors = [
                        "#fbbf24" if graph_search.lower() in n.get("name", "").lower() else c
                        for n, c in zip(filtered_nodes, node_colors)
                    ]

                fig = go.Figure(data=[go.Scatter(
                    x=[hash(n.get("name", "")) % 50 for n in filtered_nodes],
                    y=[(hash(n.get("name", "")) * 7) % 50 for n in filtered_nodes],
                    mode="markers+text",
                    text=node_names,
                    textposition="top center",
                    marker=dict(size=node_sizes, color=node_colors, line=dict(width=1, color="#fff")),
                    hoverinfo="text",
                    hovertext=[f"{n.get('name', '')}<br>类别: {n.get('category', '')}<br>连接度: {degree_map.get(n.get('name', ''), 0)}" for n in filtered_nodes],
                )])

                for e in filtered_edges:
                    s_name = e.get("source", "")
                    t_name = e.get("target", "")
                    if s_name in name_to_idx and t_name in name_to_idx:
                        rel_type = e.get("relation_type", "depends_on")
                        style = RELATION_STYLE.get(rel_type, RELATION_STYLE["depends_on"])
                        fig.add_trace(go.Scatter(
                            x=[hash(s_name) % 50, hash(t_name) % 50],
                            y=[(hash(s_name) * 7) % 50, (hash(t_name) * 7) % 50],
                            mode="lines",
                            line=dict(color=style["color"], width=1.5, dash=style["dash"]),
                            hoverinfo="none",
                            showlegend=False,
                        ))

                fig.update_layout(
                    title="知识关联图谱",
                    showlegend=False,
                    height=550,
                    margin=dict(l=20, r=20, t=40, b=20),
                    plot_bgcolor="#0B1120",
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                )
                st.plotly_chart(fig, use_container_width=True)
            except ImportError:
                st.warning("需要 plotly 来渲染知识图谱")

        with col_legend:
            st.subheader("🎨 图例")
            for cat in sorted(set(n.get("category", "未分类") for n in filtered_nodes)):
                color = cat_colors.get(cat, "#667eea")
                count = sum(1 for n in filtered_nodes if n.get("category") == cat)
                st.markdown(f'<span style="color:{color}">●</span> {cat} ({count})', unsafe_allow_html=True)

            st.divider()
            st.subheader("🔗 关系类型")
            for rel_type, style in RELATION_STYLE.items():
                dash_label = "实线" if style["dash"] == "solid" else "虚线"
                st.markdown(f'<span style="color:{style["color"]}">━━</span> {style["label"]}（{dash_label}）', unsafe_allow_html=True)

            st.divider()
            st.subheader("🔗 最多连接")
            top_nodes = sorted(degree_map.items(), key=lambda x: x[1], reverse=True)[:10]
            for name, count in top_nodes:
                st.markdown(f"**{name}** — {count} 个连接")

        if graph_search:
            matching = [n for n in filtered_nodes if graph_search.lower() in n.get("name", "").lower()]
            if matching:
                with st.expander(f"🔍 搜索结果：{len(matching)} 个匹配概念", expanded=True):
                    for n in matching:
                        st.markdown(f"**{n.get('name', '')}** — 类别: {n.get('category', '未分类')}")
                        if n.get("description"):
                            st.caption(n["description"])

with tab_query:
    st.subheader("🔍 知识查询")
    st.caption("输入自然语言问题，从知识库中检索相关内容")

    query_text = st.text_input("输入问题", placeholder="如：什么是 Transformer 架构？", key="kb_query_text")

    if st.button("搜索", type="primary", use_container_width=True, key="kb_query_btn"):
        if not query_text.strip():
            st.warning("请输入问题")
        else:
            with st.spinner("正在检索知识库..."):
                try:
                    result = post("/api/knowledge/query", {"query": query_text.strip()})
                    if isinstance(result, dict):
                        if result.get("error"):
                            st.error(f"查询失败: {result['error']}")
                        else:
                            answer = result.get("answer", "")
                            if answer:
                                st.markdown("### 💡 回答")
                                st.markdown(answer)
                            else:
                                st.info("未找到相关内容")

                            sources = result.get("sources", [])
                            if sources:
                                st.divider()
                                st.markdown("### 📚 来源页面")
                                for src in sources:
                                    title = src.get("title", "未知来源")
                                    page = src.get("page", "")
                                    link = src.get("link", "")
                                    page_info = f" (第 {page} 页)" if page else ""
                                    if link:
                                        st.markdown(f"- [{title}{page_info}]({link})")
                                    else:
                                        st.markdown(f"- {title}{page_info}")

                            confidence = result.get("confidence")
                            if confidence is not None:
                                st.divider()
                                conf_pct = int(confidence * 100)
                                conf_variant = "success" if conf_pct >= 70 else "warning" if conf_pct >= 40 else "danger"
                                st.markdown(f"**置信度：** {conf_pct}%")
                                st.progress(confidence)
                    else:
                        st.error("查询返回格式异常")
                except Exception as e:
                    st.error(f"查询失败: {e}")

with tab_status:
    try:
        stats = get("/api/knowledge/stats")
    except Exception:
        stats = {}
        st.warning("无法获取系统状态")

    if stats:
        metric_row([
            {"value": str(stats.get("total_documents", 0)), "label": "总文档数", "icon_name": "file"},
            {"value": str(stats.get("total_concepts", 0)), "label": "总概念数", "icon_name": "lightbulb"},
            {"value": str(stats.get("total_edges", 0)), "label": "总关系数", "icon_name": "link"},
            {"value": str(stats.get("wiki_pages", 0)), "label": "Wiki 页面", "icon_name": "book"},
        ])

        st.divider()

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            format_counts = stats.get("documents_by_format", {})
            if format_counts:
                try:
                    import plotly.graph_objects as go
                    labels = list(format_counts.keys())
                    values = list(format_counts.values())
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=labels,
                        values=values,
                        hole=0.4,
                        marker=dict(colors=[f"hsl({i * 60}, 60%, 60%)" for i in range(len(labels))]),
                    )])
                    fig_pie.update_layout(
                        title="文档格式分布",
                        height=350,
                        margin=dict(l=20, r=20, t=40, b=20),
                        paper_bgcolor="#0B1120",
                        font=dict(color="#94a3b8"),
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
                except ImportError:
                    st.json(format_counts)

        with col_chart2:
            edge_counts = stats.get("edges_by_relation_type", {})
            if edge_counts:
                try:
                    import plotly.graph_objects as go
                    rel_labels = list(edge_counts.keys())
                    rel_values = list(edge_counts.values())
                    rel_colors = [RELATION_STYLE.get(r, {"color": "#94a3b8"})["color"] for r in rel_labels]
                    fig_bar = go.Figure(data=[go.Bar(
                        x=rel_labels,
                        y=rel_values,
                        marker_color=rel_colors,
                    )])
                    fig_bar.update_layout(
                        title="关系类型分布",
                        height=350,
                        margin=dict(l=20, r=20, t=40, b=20),
                        paper_bgcolor="#0B1120",
                        font=dict(color="#94a3b8"),
                        plot_bgcolor="#0B1120",
                        xaxis=dict(title="关系类型"),
                        yaxis=dict(title="数量"),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
                except ImportError:
                    st.json(edge_counts)

        st.divider()

        recent_activity = stats.get("recent_activity", [])
        if recent_activity:
            st.subheader("🕐 最近活动")
            for activity in recent_activity[:20]:
                action = activity.get("action", "")
                target = activity.get("target", "")
                timestamp = activity.get("timestamp", "")
                st.markdown(f"- **{action}** {target} — {timestamp}")

        st.divider()

        st.subheader("🏥 健康检查")
        if st.button("运行 Lint 检查", type="primary", use_container_width=True, key="kb_lint_btn"):
            with st.spinner("正在运行健康检查..."):
                try:
                    lint_result = post("/api/knowledge/lint", {})
                    if isinstance(lint_result, dict):
                        if lint_result.get("error"):
                            st.error(f"检查失败: {lint_result['error']}")
                        else:
                            issues = lint_result.get("issues", [])
                            if not issues:
                                st.success("✅ 知识库状态良好，未发现问题")
                            else:
                                st.warning(f"发现 {len(issues)} 个问题")
                                for issue in issues:
                                    severity = issue.get("severity", "info")
                                    icon = "🔴" if severity == "error" else "🟡" if severity == "warning" else "🔵"
                                    st.markdown(f"{icon} **{issue.get('type', '未知')}**: {issue.get('message', '')}")
                                    if issue.get("location"):
                                        st.caption(f"位置: {issue['location']}")
                    else:
                        st.error("检查返回格式异常")
                except Exception as e:
                    st.error(f"检查失败: {e}")
    else:
        empty_state(title="无法获取系统状态", description="请确认后端服务正在运行", icon_name="server")
