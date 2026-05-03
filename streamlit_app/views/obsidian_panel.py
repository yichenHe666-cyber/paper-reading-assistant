import streamlit as st
from streamlit_app.utils.api_client import get, post
from streamlit_app.components.icon import icon
from streamlit_app.components.metric_card import metric_row
from streamlit_app.components.card import card

st.markdown(f"""
<div class="main-header">
    <h1>{icon('pen_to_square', size='lg')} Obsidian 面板</h1>
    <p>管理 Obsidian Vault 同步，扫描论文阅读状态</p>
</div>
""", unsafe_allow_html=True)

try:
    vault_status = get("/api/obsidian/status")
except Exception:
    vault_status = {}
    st.warning("无法连接后端")

exists = vault_status.get("exists", False)
metric_row([
    {"value": str(vault_status.get('paper_files', 0)), "label": "论文笔记", "icon_name": "file_lines"},
    {"value": str(vault_status.get('concept_files', 0)), "label": "概念卡片", "icon_name": "puzzle_piece"},
    {"value": str(vault_status.get('vocab_files', 0)), "label": "词汇文件", "icon_name": "book"},
    {"value": icon("check", size="sm") if exists else icon("xmark", size="sm"), "label": "Vault 连接", "icon_name": "link"},
])

st.info(f"📂 Vault 路径: `{vault_status.get('vault_path', '未知')}`")

if st.button("🔄 扫描 Obsidian Vault，同步阅读状态", use_container_width=True, type="primary"):
    with st.spinner("正在扫描 Obsidian 文件..."):
        result = post("/api/obsidian/scan-vault")
    if result.get("error"):
        st.error(f"扫描失败: {result['error']}")
    else:
        st.success(f"扫描完成！更新 {result.get('updated', 0)} 条记录，共扫描 {result.get('total', 0)} 个文件")
        if result.get("new_read", 0) > 0:
            st.balloons()
            st.info(f"发现 {result.get('new_read', 0)} 篇新读完的论文！")

st.divider()

st.subheader("💡 使用提示")
steps = [
    ("download", "首次使用：先从「首页」同步论文库"),
    ("folder_open", "选择论文：在「主题浏览」中找到想读的论文"),
    ("sparkles", "AI 生成：在「阅读工作台」点击一键生成"),
    ("upload", "写入 Obsidian：点击「写入 Obsidian」将所有内容写入 Vault"),
    ("eye", "打开 Obsidian：打开 Vault 路径即可看到新文件"),
    ("refresh", "同步状态：在 Obsidian 中修改 read_status 后，回到这里扫描同步"),
]
for step_icon, step_text in steps:
    card(content=f"""
    <div style="display:flex; align-items:center; gap:12px;">
        <div style="min-width:28px; height:28px; border-radius:50%; background:linear-gradient(135deg, var(--color-primary), var(--color-secondary)); color:#0B1120; display:flex; align-items:center; justify-content:center;">
            {icon(step_icon, size='xs')}
        </div>
        <div style="font-size:0.9rem; color:var(--color-text-secondary);">{step_text}</div>
    </div>
    """, variant="default", padding="0.75rem 1rem", margin="0 0 0.5rem 0")

st.divider()
st.subheader("💾 数据备份与导出")

col_b1, col_b2 = st.columns(2)
with col_b1:
    if st.button("📦 备份数据库", use_container_width=True):
        try:
            result = get("/api/system/backup")
            if result.get("path"):
                st.success(f"已备份到: `{result['path']}`")
            else:
                st.info("数据库尚未创建，请先同步论文库")
        except Exception as e:
            st.error(f"备份失败: {e}")

with col_b2:
    if st.button("⬇️ 导出全部为 ZIP", use_container_width=True, type="primary"):
        with st.spinner("正在打包全部数据..."):
            try:
                result = post("/api/system/export")
                if result.get("path"):
                    st.success(f"导出成功！\n\n{icon('box', size='sm')} `{result['path']}`")
                    st.info("包含：SQLite数据库 + Obsidian笔记 + Wiki知识库")
                else:
                    st.error(f"导出失败: {result.get('error', '未知错误')}")
            except Exception as e:
                st.error(f"导出失败: {e}")

st.caption("💡 每日首次启动会自动备份数据库，保留最近7天")
