import streamlit as st
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit_app.utils.api_client import get, post, patch, delete as api_delete
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state
from streamlit_app.components.badge import badge

st.markdown("""
<div class="main-header">
    <h1><i class="fa-solid fa-scale-balanced"></i> 规则设置</h1>
    <p>定义智能体行为规则，控制输出格式和安全约束</p>
</div>
""", unsafe_allow_html=True)

tab_list, tab_create, tab_import = st.tabs(["规则列表", "创建规则", "导入/导出"])

with tab_list:
    filter_cat = st.selectbox("按分类筛选", ["全部", "behavior", "output", "safety", "domain", "custom"], index=0)
    try:
        params = ""
        if filter_cat != "全部":
            params = f"?category={filter_cat}"
        rules = get(f"/api/rules{params}")
    except Exception:
        rules = []

    if not rules:
        empty_state(title="暂无规则", description="创建规则来定义智能体的行为约束", icon_name="scale-balanced")
    else:
        for r in rules:
            cat_colors = {"behavior": "info", "output": "primary", "safety": "danger", "domain": "warning", "custom": "default"}
            cat_badge = badge(r.get("category", "custom"), variant=cat_colors.get(r.get("category", "custom"), "default"))
            source_badge = badge(r.get("source", "user"), variant="success" if r.get("source") == "builtin" else "default")
            enabled_badge = badge("启用" if r.get("enabled") else "禁用", variant="success" if r.get("enabled") else "danger")
            card(
                content=f"""
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:600; color:var(--color-text-primary);">
                            {r.get('name', 'N/A')} {cat_badge} {source_badge} {enabled_badge}
                        </div>
                        <div style="font-size:0.85rem; color:var(--color-text-secondary); margin-top:4px;">
                            {r.get('description', '')}
                        </div>
                        <div style="font-size:0.75rem; color:var(--color-text-muted); margin-top:2px;">
                            优先级: {r.get('priority', 50)} · 作用域: {r.get('scope', 'global')}
                        </div>
                    </div>
                </div>
                """,
                variant="default",
                padding="1rem 1.5rem",
                margin="0 0 0.8rem 0",
            )
            col_t, col_d = st.columns([3, 1])
            with col_t:
                toggle_label = "禁用" if r.get("enabled") else "启用"
                if st.button(toggle_label, key=f"toggle_rule_{r['id']}"):
                    result = patch(f"/api/rules/{r['id']}/toggle", {})
                    if "error" not in result:
                        st.success(f"已{toggle_label}")
                        st.rerun()
            with col_d:
                if r.get("source") != "builtin":
                    if st.button("🗑️", key=f"del_rule_{r['id']}", help="删除此规则"):
                        result = api_delete(f"/api/rules/{r['id']}")
                        if "error" not in result:
                            st.success("已删除")
                            st.rerun()
            with st.expander(f"查看内容 — {r.get('name', '')}"):
                st.markdown(r.get("content", ""))

with tab_create:
    with st.form("create_rule_form"):
        rule_name = st.text_input("规则名称", placeholder="例如：no-hallucination")
        rule_desc = st.text_input("描述", placeholder="简要描述规则的作用")
        rule_content = st.text_area("规则内容 (Markdown)", placeholder="# 规则标题\n\n规则详细内容...", height=200)
        col_a, col_b = st.columns(2)
        with col_a:
            rule_category = st.selectbox("分类", ["behavior", "output", "safety", "domain", "custom"], index=4)
            rule_priority = st.number_input("优先级", min_value=0, max_value=100, value=50)
        with col_b:
            rule_scope = st.selectbox("作用域", ["global", "workspace", "session"], index=0)
            rule_conflict = st.selectbox("冲突解决", ["highest_priority", "latest", "merge"], index=0)
        submitted = st.form_submit_button("创建规则", use_container_width=True, type="primary")
        if submitted:
            if not rule_name.strip() or not rule_content.strip():
                st.error("名称和内容不能为空")
            else:
                result = post("/api/rules", {
                    "name": rule_name.strip(),
                    "description": rule_desc.strip(),
                    "content": rule_content.strip(),
                    "category": rule_category,
                    "priority": rule_priority,
                    "scope": rule_scope,
                    "conflict_resolution": rule_conflict,
                })
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(f"规则「{rule_name}」创建成功！")
                    st.rerun()

with tab_import:
    st.markdown("#### 导出规则")
    if st.button("导出所有规则为 JSON", use_container_width=True):
        try:
            rules_data = get("/api/rules/export")
            st.download_button(
                "下载规则文件",
                data=json.dumps(rules_data, ensure_ascii=False, indent=2),
                file_name="agent_rules.json",
                mime="application/json",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"导出失败: {e}")

    st.markdown("---")
    st.markdown("#### 导入规则")
    uploaded = st.file_uploader("上传规则 JSON 文件", type=["json"])
    if uploaded:
        try:
            rules_data = json.loads(uploaded.read().decode("utf-8"))
            if isinstance(rules_data, list):
                overwrite = st.checkbox("覆盖同名规则")
                if st.button("导入", use_container_width=True, type="primary"):
                    result = post("/api/rules/import", {"rules": rules_data, "overwrite": overwrite})
                    st.success(f"导入完成: 成功 {result.get('imported', 0)}, 跳过 {result.get('skipped', 0)}")
                    if result.get("errors"):
                        for err in result["errors"]:
                            st.warning(err)
                    st.rerun()
            else:
                st.error("文件格式错误，应为规则数组")
        except json.JSONDecodeError:
            st.error("JSON 解析失败")
