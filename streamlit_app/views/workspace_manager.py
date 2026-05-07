import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit_app.utils.api_client import get, post, patch, delete as api_delete
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
from streamlit_app.components.empty_state import empty_state
from streamlit_app.components.badge import badge

st.markdown("""
<div class="main-header">
    <h1><i class="fa-solid fa-layer-group"></i> 工作空间</h1>
    <p>管理项目级工作空间，关联对话、论文和资源</p>
</div>
""", unsafe_allow_html=True)

tab_list, tab_create = st.tabs(["工作空间列表", "创建工作空间"])

with tab_create:
    with st.form("create_workspace_form"):
        ws_name = st.text_input("名称", placeholder="例如：BFT共识研究")
        ws_desc = st.text_area("描述", placeholder="工作空间描述...", height=80)
        ws_path = st.text_input("项目根路径", placeholder="例如：C:\\Projects\\bft-research")
        ws_icon = st.text_input("图标 (Font Awesome)", value="fa-flask")
        ws_color = st.color_picker("主题色", value="#667eea")
        submitted = st.form_submit_button("创建工作空间", use_container_width=True, type="primary")
        if submitted:
            if not ws_name.strip():
                st.error("请输入工作空间名称")
            else:
                result = post("/api/workspaces", {
                    "name": ws_name.strip(),
                    "description": ws_desc.strip(),
                    "root_path": ws_path.strip(),
                    "icon": ws_icon.strip(),
                    "color": ws_color,
                })
                if "error" in result:
                    st.error(result["error"])
                else:
                    st.success(f"工作空间「{ws_name}」创建成功！")
                    st.rerun()

with tab_list:
    try:
        workspaces = get("/api/workspaces")
    except Exception:
        workspaces = []

    if not workspaces:
        empty_state(title="暂无工作空间", description="创建你的第一个工作空间来组织研究项目", icon_name="layer-group")
    else:
        for ws in workspaces:
            is_default = ws.get("is_default", False)
            default_badge = badge("默认", variant="primary", size="xs") if is_default else ""
            stats = ws.get("stats", {})
            card(
                content=f"""
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:600; color:var(--color-text-primary); font-size:1rem;">
                            <i class="fa-solid {ws.get('icon', 'fa-folder')}"></i> {ws.get('name', 'N/A')}
                            {default_badge}
                        </div>
                        <div style="font-size:0.85rem; color:var(--color-text-secondary); margin-top:4px;">
                            {ws.get('description', '无描述')}
                        </div>
                        <div style="font-size:0.8rem; color:var(--color-text-muted); margin-top:4px;">
                            会话: {stats.get('session_count', 0)} · 消息: {stats.get('message_count', 0)}
                        </div>
                    </div>
                </div>
                """,
                variant="default",
                padding="1rem 1.5rem",
                margin="0 0 0.8rem 0",
            )
            col_e, col_d = st.columns([3, 1])
            with col_e:
                if st.button("编辑", key=f"edit_ws_{ws['id']}"):
                    new_name = st.text_input("新名称", value=ws.get("name", ""), key=f"ws_name_{ws['id']}")
                    new_desc = st.text_area("新描述", value=ws.get("description", ""), key=f"ws_desc_{ws['id']}")
                    if st.button("保存", key=f"save_ws_{ws['id']}"):
                        result = patch(f"/api/workspaces/{ws['id']}", {"name": new_name, "description": new_desc})
                        if "error" not in result:
                            st.success("已更新")
                            st.rerun()
            with col_d:
                if not is_default:
                    if st.button("🗑️", key=f"del_ws_{ws['id']}", help="删除此工作空间"):
                        result = api_delete(f"/api/workspaces/{ws['id']}")
                        if "error" not in result:
                            st.success("已删除")
                            st.rerun()
