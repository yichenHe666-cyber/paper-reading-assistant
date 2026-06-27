import streamlit as st
from urllib.parse import quote
from streamlit_app.utils.api_client import get, post, patch, upload_pdf
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.badge import badge
from streamlit_app.components.empty_state import empty_state

st.markdown("""
<div class="main-header">
    <h1>🧩 技能管理</h1>
    <p>导入、管理和下载 LLM 技能，扩展核动力科研牛马的分析能力</p>
</div>
""", unsafe_allow_html=True)

SOURCE_LABELS = {
    "builtin": ("内置", "primary"),
    "imported": ("导入", "info"),
    "clawhub": ("ClawHub", "success"),
}

tab_installed, tab_import, tab_clawhub = st.tabs([
    "📋 已安装技能",
    "📤 导入技能",
    "🛒 ClawHub 商店",
])

with tab_installed:
    col_filter1, col_filter2, col_search = st.columns([1, 1, 2])
    with col_filter1:
        source_filter = st.selectbox("来源", ["全部", "内置", "导入", "ClawHub"], key="skill_source_filter")
    with col_filter2:
        status_filter = st.selectbox("状态", ["全部", "已启用", "已禁用"], key="skill_status_filter")
    with col_search:
        search_q = st.text_input("搜索技能", placeholder="输入技能名称...", key="skill_search")

    params = {}
    if source_filter != "全部":
        source_map = {"内置": "builtin", "导入": "imported", "ClawHub": "clawhub"}
        params["source"] = source_map[source_filter]
    if status_filter == "已启用":
        params["enabled"] = "true"
    elif status_filter == "已禁用":
        params["enabled"] = "false"
    if search_q:
        params["q"] = search_q

    try:
        query_str = "&".join(f"{k}={v}" for k, v in params.items())
        skills = get(f"/api/skills?{query_str}") if params else get("/api/skills")
        if not isinstance(skills, list):
            skills = []
    except Exception:
        skills = []

    if not skills:
        empty_state(title="暂无技能", description="导入自定义技能或从 ClawHub 下载社区技能", icon_name="puzzle-piece")
    else:
        st.caption(f"共 {len(skills)} 个技能")
        for skill in skills:
            source_label, source_variant = SOURCE_LABELS.get(skill.get("source"), ("未知", "default"))
            enabled_icon = "🟢" if skill.get("enabled") else "🔴"
            enabled_text = "已启用" if skill.get("enabled") else "已禁用"

            desc = skill.get("description")
            if desc and len(desc) > 80:
                desc = desc[:80] + "..."

            with st.container():
                col_info, col_actions = st.columns([4, 1])
                with col_info:
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                        <span style="font-size:1.05rem; font-weight:600;">{enabled_icon} {skill['name']}</span>
                    </div>
                    <div style="color:var(--color-text-secondary); font-size:0.875rem; margin-bottom:6px;">{desc}</div>
                    """, unsafe_allow_html=True)
                    badge(source_label, variant=source_variant)
                    badge(enabled_text, variant="success" if skill.get("enabled") else "danger")

                with col_actions:
                    if st.button("查看详情", key=f"detail_{skill['id']}", use_container_width=True):
                        st.session_state[f"skill_detail_{skill['id']}"] = not st.session_state.get(f"skill_detail_{skill['id']}", False)

                    if skill.get("enabled"):
                        if st.button("禁用", key=f"disable_{skill['id']}", use_container_width=True):
                            result = patch(f"/api/skills/{skill['id']}/toggle", {})
                            if "error" not in result:
                                st.success(f"已禁用技能「{skill['name']}」")
                                st.rerun()
                    else:
                        if st.button("启用", key=f"enable_{skill['id']}", use_container_width=True, type="primary"):
                            result = patch(f"/api/skills/{skill['id']}/toggle", {})
                            if "error" not in result:
                                st.success(f"已启用技能「{skill['name']}」")
                                st.rerun()

                    if skill.get("source") != "builtin":
                        if st.button("删除", key=f"delete_{skill['id']}", use_container_width=True):
                            st.session_state[f"confirm_delete_{skill['id']}"] = True

                    if skill.get("source") == "builtin":
                        st.caption("内置技能不可删除")

                if st.session_state.get(f"confirm_delete_{skill['id']}", False):
                    st.warning(f"确定要删除技能「{skill['name']}」吗？此操作不可恢复。")
                    col_y, col_n = st.columns(2)
                    with col_y:
                        if st.button("确认删除", key=f"confirm_yes_{skill['id']}", type="primary", use_container_width=True):
                            from streamlit_app.utils.api_client import delete as api_delete
                            result = api_delete(f"/api/skills/{skill['id']}")
                            st.session_state[f"confirm_delete_{skill['id']}"] = False
                            if "error" not in result:
                                st.success(f"已删除技能「{skill['name']}」")
                                st.rerun()
                            else:
                                st.error(result["error"])
                    with col_n:
                        if st.button("取消", key=f"confirm_no_{skill['id']}", use_container_width=True):
                            st.session_state[f"confirm_delete_{skill['id']}"] = False
                            st.rerun()

                if st.session_state.get(f"skill_detail_{skill['id']}", False):
                    with st.expander("技能详情", expanded=True):
                        try:
                            detail = get(f"/api/skills/{skill['id']}")
                            st.markdown(detail.get("content", ""))
                            st.divider()
                            meta_col1, meta_col2 = st.columns(2)
                            with meta_col1:
                                st.caption(f"来源: {source_label}")
                                st.caption(f"创建时间: {detail.get('created_at', '-')}")
                            with meta_col2:
                                st.caption(f"ClawHub 版本: {detail.get('clawhub_version', '-')}")
                                st.caption(f"更新时间: {detail.get('updated_at', '-')}")
                            if detail.get("metadata"):
                                st.json(detail["metadata"])
                        except Exception as e:
                            st.error(f"加载详情失败: {e}")

                st.divider()

with tab_import:
    st.subheader("导入自定义技能")
    st.caption("上传 SKILL.md 文件或直接粘贴技能内容，技能文件必须包含 YAML frontmatter（--- 包裹的头部），且至少包含 name 和 description 字段。")

    import_col1, import_col2 = st.columns(2)

    with import_col1:
        st.markdown("#### 📁 文件上传")
        uploaded_file = st.file_uploader(
            "选择 SKILL.md 文件",
            type=["md", "txt", "markdown"],
            key="skill_file_upload",
        )
        if uploaded_file is not None:
            file_content = uploaded_file.read().decode("utf-8")
            st.code(file_content[:500] + ("..." if len(file_content) > 500 else ""), language="markdown")
            if st.button("导入文件", key="import_file_btn", type="primary", use_container_width=True):
                result = post("/api/skills/import", {"content": file_content})
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(f"技能「{result.get('name', '')}」导入成功！({result.get('action', '')})")

    with import_col2:
        st.markdown("#### ✏️ 文本粘贴")
        pasted_content = st.text_area(
            "粘贴技能内容",
            placeholder="---\nname: my-skill\ndescription: 我的自定义技能\n---\n\n# My Skill\n\n技能说明...",
            height=300,
            key="skill_paste",
        )
        if st.button("导入文本", key="import_paste_btn", type="primary", use_container_width=True):
            if not pasted_content.strip():
                st.error("请输入技能内容")
            else:
                result = post("/api/skills/import", {"content": pasted_content})
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(f"技能「{result.get('name', '')}」导入成功！({result.get('action', '')})")

    with st.expander("SKILL.md 格式说明"):
        st.markdown("""
        ```markdown
        ---
        name: my-custom-skill
        description: 我的自定义分析技能
        metadata:
          openclaw:
            emoji: "🔧"
            requires:
              env: ["MY_API_KEY"]
        ---

        # My Custom Skill

        你是一位专业的分析助手...

        ## 使用方式
        当用户需要...时，使用此技能：

        1. 步骤一
        2. 步骤二

        ## 输出格式
        返回 JSON 格式的分析结果...
        ```
        """)

with tab_clawhub:
    st.subheader("ClawHub 技能商店")
    st.caption("从 ClawHub 中国镜像站搜索和安装社区技能")

    search_col1, search_col2 = st.columns([4, 1])
    with search_col1:
        clawhub_q = st.text_input("搜索技能", placeholder="输入关键词搜索 ClawHub 技能...", key="clawhub_search")
    with search_col2:
        st.markdown("<div style='height:1.75rem;'></div>", unsafe_allow_html=True)
        search_btn = st.button("搜索", key="clawhub_search_btn", use_container_width=True, type="primary")

    if search_btn and clawhub_q:
        with st.spinner("搜索中..."):
            try:
                results = get(f"/api/skills/clawhub/search?q={quote(clawhub_q)}")
                if isinstance(results, dict) and "error" in results:
                    st.error(f"搜索失败: {results['error']}")
                elif isinstance(results, list) and len(results) > 0:
                    st.success(f"找到 {len(results)} 个技能")
                    for r in results:
                        with st.container():
                            r_col1, r_col2 = st.columns([4, 1])
                            with r_col1:
                                st.markdown(f"**{r.get('name', r.get('slug', '未知'))}**")
                                st.caption(r.get("description", "暂无描述"))
                                meta_parts = []
                                if r.get("author"):
                                    meta_parts.append(f"作者: {r['author']}")
                                if r.get("downloads") is not None:
                                    meta_parts.append(f"下载量: {r['downloads']}")
                                if r.get("rating") is not None:
                                    meta_parts.append(f"评分: {r['rating']}")
                                if meta_parts:
                                    st.caption(" | ".join(meta_parts))
                            with r_col2:
                                slug = r.get("slug", r.get("name", ""))
                                try:
                                    installed = get("/api/skills")
                                    is_installed = any(
                                        s.get("clawhub_slug") == slug or s.get("slug") == slug
                                        for s in installed
                                    )
                                except Exception:
                                    is_installed = False

                                if is_installed:
                                    badge("已安装", variant="success")
                                else:
                                    if st.button("安装", key=f"install_{slug}", use_container_width=True):
                                        result = post("/api/skills/clawhub/install", {"slug": slug})
                                        if "error" in result:
                                            st.error(f"安装失败: {result['error']}")
                                        else:
                                            st.success(f"技能「{result.get('name', slug)}」安装成功！")
                                            st.rerun()
                            st.divider()
                else:
                    empty_state(title="未找到技能", description=f"没有找到与「{clawhub_q}」相关的技能", icon_name="magnifying-glass")
            except Exception as e:
                st.error(f"搜索失败: {e}")

    if not search_btn:
        st.markdown("#### 精选技能")
        with st.spinner("加载精选技能..."):
            try:
                featured = get("/api/skills/clawhub/search?q=featured")
                if isinstance(featured, dict) and "error" in featured:
                    st.info("暂无法加载精选技能，请检查网络连接")
                elif isinstance(featured, list) and len(featured) > 0:
                    for r in featured[:6]:
                        with st.container():
                            r_col1, r_col2 = st.columns([4, 1])
                            with r_col1:
                                st.markdown(f"**{r.get('name', r.get('slug', '未知'))}**")
                                st.caption(r.get("description", "暂无描述")[:100])
                            with r_col2:
                                slug = r.get("slug", r.get("name", ""))
                                if st.button("安装", key=f"feat_install_{slug}", use_container_width=True):
                                    result = post("/api/skills/clawhub/install", {"slug": slug})
                                    if "error" in result:
                                        st.error(f"安装失败: {result['error']}")
                                    else:
                                        st.success(f"技能「{result.get('name', slug)}」安装成功！")
                            st.divider()
                else:
                    st.info("暂无精选技能数据")
            except Exception:
                st.info("无法连接 ClawHub 镜像站，请检查网络连接")

    st.divider()
    if st.button("检查 ClawHub 技能更新", key="check_updates_btn", use_container_width=True):
        with st.spinner("检查更新中..."):
            try:
                updates = post("/api/skills/clawhub/check-updates", {})
                if isinstance(updates, dict) and "error" in updates:
                    st.error(f"检查更新失败: {updates['error']}")
                elif isinstance(updates, list) and len(updates) > 0:
                    st.warning(f"发现 {len(updates)} 个技能有新版本")
                    for u in updates:
                        st.markdown(f"- **{u['name']}**: {u.get('local_version', '未知')} → {u.get('remote_version', '未知')}")
                else:
                    st.success("所有 ClawHub 技能均为最新版本")
            except Exception as e:
                st.error(f"检查更新失败: {e}")
