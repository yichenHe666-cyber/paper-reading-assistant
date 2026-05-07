import json
import streamlit as st
from streamlit_app.utils.api_client import get, post, put, delete
from streamlit_app.components.badge import badge, badge_group
from streamlit_app.components.empty_state import empty_state
from streamlit_app.components.metric_card import metric_row
from streamlit_app.components.icon import icon

MEMORY_TYPES = {
    "preference": ("偏好记忆", "primary"),
    "experience": ("经验记忆", "success"),
    "direction": ("方向记忆", "warning"),
    "connection": ("关联记忆", "info"),
}

SOURCE_LABELS = {
    "auto_distill": ("自动蒸馏", "info"),
    "user_manual": ("手动创建", "success"),
    "llm_suggest": ("LLM 建议", "warning"),
}

FRESHNESS_LABELS = {
    "stable": ("稳定", "success"),
    "strengthening": ("增强中", "primary"),
    "weakening": ("减弱中", "warning"),
    "stale": ("过时", "danger"),
}

st.markdown("""
<div class="main-header">
    <h1>🧠 记忆面板</h1>
    <p>管理偏好、经验、方向与关联记忆，查看蒸馏历史</p>
</div>
""", unsafe_allow_html=True)

try:
    stats = get("/api/memory/stats")
except Exception:
    stats = {}
    st.warning("无法连接后端服务")

type_counts = stats.get("by_type", {})
metric_row([
    {"value": str(type_counts.get("preference", 0)), "label": "偏好记忆", "icon_name": "heart"},
    {"value": str(type_counts.get("experience", 0)), "label": "经验记忆", "icon_name": "lightbulb"},
    {"value": str(type_counts.get("direction", 0)), "label": "方向记忆", "icon_name": "compass"},
    {"value": str(type_counts.get("connection", 0)), "label": "关联记忆", "icon_name": "link"},
])

st.divider()

with st.expander("➕ 添加记忆", expanded=False):
    with st.form("add_memory"):
        add_type = st.selectbox("记忆类型", options=list(MEMORY_TYPES.keys()),
                                format_func=lambda x: MEMORY_TYPES[x][0])
        add_title = st.text_input("标题")
        add_content = st.text_area("内容", height=150)
        add_tags = st.text_input("标签（逗号分隔）")
        add_confidence = st.slider("置信度", min_value=0.0, max_value=1.0, step=0.1, value=1.0)
        submitted = st.form_submit_button("添加", type="primary", use_container_width=True)

        if submitted:
            if not add_title.strip():
                st.error("标题不能为空")
            elif not add_content.strip():
                st.error("内容不能为空")
            else:
                tags_list = [t.strip() for t in add_tags.split(",") if t.strip()] if add_tags else []
                payload = {
                    "memory_type": add_type,
                    "title": add_title.strip(),
                    "content": add_content.strip(),
                    "tags": tags_list,
                    "confidence": add_confidence,
                }
                try:
                    result = post("/api/memory", payload)
                    if isinstance(result, dict) and result.get("error"):
                        st.error(f"添加失败: {result['error']}")
                    else:
                        st.success("记忆添加成功！")
                        st.rerun()
                except Exception as e:
                    st.error(f"添加失败: {e}")

st.divider()

col_f1, col_f2, col_f3, col_f4 = st.columns([1, 1, 2, 1])
with col_f1:
    type_filter = st.selectbox("记忆类型", ["全部"] + list(MEMORY_TYPES.keys()),
                               format_func=lambda x: "全部" if x == "全部" else MEMORY_TYPES[x][0],
                               key="mem_type_filter")
with col_f2:
    source_filter = st.selectbox("来源类型", ["全部"] + list(SOURCE_LABELS.keys()),
                                 format_func=lambda x: "全部" if x == "全部" else SOURCE_LABELS[x][0],
                                 key="mem_source_filter")
with col_f3:
    search_q = st.text_input("搜索", placeholder="输入关键词搜索记忆...", key="mem_search")
with col_f4:
    show_inactive = st.toggle("显示已删除", value=False, key="mem_show_inactive")

params = {}
if type_filter != "全部":
    params["memory_type"] = type_filter
if source_filter != "全部":
    params["source_type"] = source_filter
if search_q:
    params["q"] = search_q
if show_inactive:
    params["is_active"] = "false"
else:
    params["is_active"] = "true"
params["limit"] = 100

tab_list, tab_observations, tab_distill = st.tabs(["记忆列表", "观察合并", "蒸馏历史"])

with tab_list:
    if st.session_state.get("editing_memory_id"):
        mem_id = st.session_state.editing_memory_id
        try:
            detail = get(f"/api/memory/{mem_id}")
            if isinstance(detail, dict) and detail.get("error"):
                st.error(f"加载记忆失败: {detail['error']}")
                st.session_state.editing_memory_id = None
            else:
                st.subheader(f"✏️ 编辑记忆: {detail.get('title', '')}")
                edit_title = st.text_input("标题", value=detail.get("title", ""), key="edit_mem_title")
                edit_content = st.text_area("内容", value=detail.get("content", ""), height=150, key="edit_mem_content")
                edit_tags = st.text_input("标签（逗号分隔）",
                                          value=",".join(detail.get("tags", [])),
                                          key="edit_mem_tags")
                edit_confidence = st.slider("置信度", min_value=0.0, max_value=1.0, step=0.1,
                                            value=detail.get("confidence", 1.0), key="edit_mem_confidence")

                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("💾 保存", type="primary", use_container_width=True, key="edit_mem_save"):
                        if not edit_title.strip():
                            st.error("标题不能为空")
                        else:
                            tags_list = [t.strip() for t in edit_tags.split(",") if t.strip()] if edit_tags else []
                            payload = {
                                "title": edit_title.strip(),
                                "content": edit_content.strip(),
                                "tags": tags_list,
                                "confidence": edit_confidence,
                            }
                            try:
                                result = put(f"/api/memory/{mem_id}", payload)
                                if isinstance(result, dict) and result.get("error"):
                                    st.error(f"保存失败: {result['error']}")
                                else:
                                    st.success("记忆更新成功！")
                                    st.session_state.editing_memory_id = None
                                    st.rerun()
                            except Exception as e:
                                st.error(f"保存失败: {e}")
                with col_cancel:
                    if st.button("取消", use_container_width=True, key="edit_mem_cancel"):
                        st.session_state.editing_memory_id = None
                        st.rerun()

                st.divider()
        except Exception as e:
            st.error(f"加载记忆失败: {e}")
            st.session_state.editing_memory_id = None

    query_str = "&".join(f"{k}={v}" for k, v in params.items())
    try:
        memories = get(f"/api/memory?{query_str}")
        if not isinstance(memories, list):
            memories = []
    except Exception:
        memories = []

    if not memories:
        empty_state(title="暂无记忆", description="添加第一条记忆或调整筛选条件", icon_name="brain")
    else:
        st.caption(f"共 {len(memories)} 条记忆")
        for mem in memories:
            type_label, type_variant = MEMORY_TYPES.get(mem.get("memory_type", ""), ("未知", "default"))
            source_label, source_variant = SOURCE_LABELS.get(mem.get("source_type", ""), ("未知", "default"))
            confidence_val = mem.get("confidence", 1.0)
            confidence_pct = int(confidence_val * 100)
            access_count = mem.get("access_count", 0)
            tags = mem.get("tags", [])

            header = f"{type_label} · {mem.get('title', '无标题')}"
            with st.expander(header):
                st.markdown(mem.get("content", ""))

                tag_col, source_col = st.columns([3, 1])
                with tag_col:
                    if tags:
                        badge_group(tags, variant="default")
                with source_col:
                    badge(source_label, variant=source_variant)

                conf_col, access_col = st.columns(2)
                with conf_col:
                    st.progress(confidence_val, text=f"置信度: {confidence_pct}%")
                with access_col:
                    st.caption(f"访问次数: {access_count}")

                if mem.get("source_paper_id"):
                    st.caption(f"来源论文: {mem['source_paper_id']}")

                if mem.get("created_at"):
                    st.caption(f"创建时间: {mem['created_at']}")

                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("✏️ 编辑", key=f"edit_{mem['id']}", use_container_width=True):
                        st.session_state.editing_memory_id = mem["id"]
                        st.rerun()
                with btn_col2:
                    if st.button("🗑️ 删除", key=f"del_{mem['id']}", use_container_width=True):
                        st.session_state[f"confirm_del_{mem['id']}"] = True

                if st.session_state.get(f"confirm_del_{mem['id']}", False):
                    st.warning("确定要删除这条记忆吗？此为软删除，可恢复。")
                    col_y, col_n = st.columns(2)
                    with col_y:
                        if st.button("确认删除", key=f"yes_del_{mem['id']}", type="primary", use_container_width=True):
                            try:
                                result = delete(f"/api/memory/{mem['id']}")
                                if isinstance(result, dict) and result.get("error"):
                                    st.error(f"删除失败: {result['error']}")
                                else:
                                    st.success("记忆已删除")
                                    st.session_state[f"confirm_del_{mem['id']}"] = False
                                    st.rerun()
                            except Exception as e:
                                st.error(f"删除失败: {e}")
                    with col_n:
                        if st.button("取消", key=f"no_del_{mem['id']}", use_container_width=True):
                            st.session_state[f"confirm_del_{mem['id']}"] = False
                            st.rerun()

    st.divider()
    st.subheader("🤔 反思推理")
    st.caption("对记忆进行深度推理，发现新见解、矛盾和趋势")
    reflect_query = st.text_input("反思主题", placeholder="输入想反思的问题或主题...", key="reflect_query_input")
    reflect_entity = st.text_input("关联实体（可选）", placeholder="如：PBFT、分布式系统...", key="reflect_entity_input")
    reflect_save = st.checkbox("保存反思结果为记忆", value=False, key="reflect_save_check")
    if st.button("🤔 执行反思", type="primary", use_container_width=True, key="trigger_reflect"):
        if reflect_query.strip():
            with st.spinner("正在深度反思..."):
                try:
                    payload = {
                        "query": reflect_query.strip(),
                        "save_as_memory": reflect_save,
                    }
                    if reflect_entity.strip():
                        payload["entity_name"] = reflect_entity.strip()
                    result = post("/api/memory/reflect", payload)
                    if isinstance(result, dict):
                        if result.get("saved_memory_id"):
                            st.success(f"反思完成并已保存为记忆 (ID: {result['saved_memory_id']})")
                        insights = result.get("insights", [])
                        contradictions = result.get("contradictions", [])
                        trends = result.get("trends", [])
                        actions = result.get("actions", [])
                        if insights:
                            st.markdown("**💡 新见解**")
                            for ins in insights:
                                st.markdown(f"- {ins}")
                        if contradictions:
                            st.markdown("**⚠️ 矛盾发现**")
                            for c in contradictions:
                                st.markdown(f"- {c}")
                        if trends:
                            st.markdown("**📈 趋势预测**")
                            for t in trends:
                                st.markdown(f"- {t}")
                        if actions:
                            st.markdown("**🎯 行动建议**")
                            for a in actions:
                                st.markdown(f"- {a}")
                    else:
                        st.error("反思失败")
                except Exception as e:
                    st.error(f"反思失败: {e}")
        else:
            st.warning("请输入反思主题")

with tab_observations:
    st.subheader("观察合并")
    st.caption("自动将同一实体的多条记忆合并为精炼的观察，带证据溯源和新鲜度趋势")

    col_obs1, col_obs2 = st.columns([3, 1])
    with col_obs1:
        obs_entity_filter = st.text_input("按实体名筛选", placeholder="输入实体名...", key="obs_entity_filter")
    with col_obs2:
        obs_trend_filter = st.selectbox("新鲜度趋势", ["全部", "stable", "strengthening", "weakening", "stale"],
                                        format_func=lambda x: "全部" if x == "全部" else FRESHNESS_LABELS.get(x, (x, "default"))[0],
                                        key="obs_trend_filter")

    obs_params = {"limit": 100}
    if obs_entity_filter:
        obs_params["entity_name"] = obs_entity_filter
    if obs_trend_filter != "全部":
        obs_params["freshness_trend"] = obs_trend_filter

    obs_query_str = "&".join(f"{k}={v}" for k, v in obs_params.items())
    try:
        obs_data = get(f"/api/memory/observations?{obs_query_str}")
        observations = obs_data.get("observations", []) if isinstance(obs_data, dict) else []
    except Exception:
        observations = []

    if not observations:
        empty_state(title="暂无观察", description="当同一实体有3条以上记忆时，可触发合并生成观察", icon_name="eye")
    else:
        st.caption(f"共 {len(observations)} 条观察")
        for obs in observations:
            trend_label, trend_variant = FRESHNESS_LABELS.get(obs.get("freshness_trend", "stable"), ("未知", "default"))
            header = f"🔍 {obs.get('entity_name', '未知')} · 证据{obs.get('proof_count', 0)}条 · {trend_label}"
            with st.expander(header):
                st.markdown(obs.get("content", ""))
                if obs.get("evidence_quotes"):
                    st.markdown("**证据引用：**")
                    try:
                        quotes = json.loads(obs["evidence_quotes"]) if isinstance(obs["evidence_quotes"], str) else obs["evidence_quotes"]
                        for q in quotes[:5]:
                            st.markdown(f"> {q}")
                    except Exception:
                        pass
                conf_val = obs.get("confidence", 0.8)
                st.progress(conf_val, text=f"置信度: {int(conf_val * 100)}%")
                if obs.get("created_at"):
                    st.caption(f"创建: {obs['created_at']}")

    st.divider()
    st.subheader("手动合并")
    consolidate_entity = st.text_input("输入实体名进行合并", placeholder="如：PBFT、共识算法...", key="consolidate_entity_input")
    if st.button("🔄 触发合并", type="primary", use_container_width=True, key="trigger_consolidate"):
        if consolidate_entity.strip():
            with st.spinner("正在合并观察..."):
                try:
                    result = post("/api/memory/observations/consolidate", {"entity_name": consolidate_entity.strip()})
                    if isinstance(result, dict) and result.get("status") == "ok":
                        st.success(f"合并成功！观察 ID: {result.get('observation_id')}")
                        st.rerun()
                    else:
                        st.info(result.get("reason", "合并跳过"))
                except Exception as e:
                    st.error(f"合并失败: {e}")
        else:
            st.warning("请输入实体名")

    if st.button("🔄 全量合并扫描", use_container_width=True, key="trigger_full_consolidate"):
        with st.spinner("正在扫描并合并..."):
            try:
                result = post("/api/memory/observations/consolidate", {})
                if isinstance(result, dict):
                    st.success(f"合并完成！成功: {result.get('consolidated', 0)}，失败: {result.get('failed', 0)}")
                    st.rerun()
            except Exception as e:
                st.error(f"合并失败: {e}")

with tab_distill:
    st.subheader("蒸馏历史")
    st.caption("从论文中蒸馏提取记忆，将阅读经验转化为可复用的知识")

    try:
        papers = get("/api/papers?limit=200")
        if not isinstance(papers, list):
            papers = []
    except Exception:
        papers = []

    paper_options = {}
    if papers:
        for p in papers:
            pid = p.get("id", "")
            title = p.get("title", "无标题")
            if len(title) > 60:
                title = title[:60] + "..."
            paper_options[pid] = title

    if paper_options:
        selected_paper = st.selectbox(
            "选择论文",
            options=list(paper_options.keys()),
            format_func=lambda x: paper_options.get(x, x),
            key="distill_paper_select",
        )

        if st.button("🔥 触发蒸馏", type="primary", use_container_width=True, key="trigger_distill"):
            with st.spinner("正在蒸馏记忆，请稍候..."):
                try:
                    result = post(f"/api/memory/distill/{selected_paper}", {})
                    if isinstance(result, dict) and result.get("error"):
                        st.error(f"蒸馏失败: {result['error']}")
                    else:
                        created = result.get("created", 0)
                        st.success(f"蒸馏完成！生成 {created} 条记忆")
                        if result.get("memories"):
                            for m in result["memories"]:
                                type_label, type_variant = MEMORY_TYPES.get(m.get("memory_type", ""), ("未知", "default"))
                                badge(type_label, variant=type_variant)
                                st.markdown(f"**{m.get('title', '')}**")
                                st.caption(m.get("content", "")[:200])
                                st.divider()
                except Exception as e:
                    st.error(f"蒸馏失败: {e}")
    else:
        empty_state(title="暂无论文", description="请先在「主题浏览」中同步论文库", icon_name="file-lines")

    st.divider()
    st.subheader("嵌入回填")
    st.caption("为已有记忆生成向量嵌入，启用语义检索功能")
    if st.button("🔢 开始回填", use_container_width=True, key="trigger_backfill"):
        with st.spinner("正在回填嵌入向量..."):
            try:
                result = post("/api/memory/backfill-embeddings", {})
                if isinstance(result, dict):
                    st.success(f"回填完成！处理: {result.get('processed', 0)}，失败: {result.get('failed', 0)}")
            except Exception as e:
                st.error(f"回填失败: {e}")
