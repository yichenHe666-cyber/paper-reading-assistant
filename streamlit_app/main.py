import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

st.set_page_config(page_title="核动力科研牛马", layout="wide")

# ── Aggressive CSS override for sidebar collapsed layout ──
st.markdown("""
<style>
/* When sidebar is collapsed, force sidebar itself to zero width
   so the flex layout gives all space to the main content. */
section[data-testid="stSidebar"][aria-expanded="false"] {
    width: 0px !important;
    min-width: 0px !important;
    max-width: 0px !important;
    flex-basis: 0px !important;
    padding: 0px !important;
    border: none !important;
    overflow: hidden !important;
}
/* Main content siblings should also drop any leftover margin */
section[data-testid="stSidebar"][aria-expanded="false"] ~ div {
    margin-left: 0px !important;
}
</style>
""", unsafe_allow_html=True)

# ── Inject design tokens & global CSS ─────────────────────
from assets.custom_theme import inject_theme
inject_theme()

# ── Session state init ─────────────────────────────────────
if "selected_topic" not in st.session_state:
    st.session_state.selected_topic = None
if "_navigate_to_topic" not in st.session_state:
    st.session_state["_navigate_to_topic"] = None
if "selected_paper_id" not in st.session_state:
    st.session_state.selected_paper_id = None
if "generated" not in st.session_state:
    st.session_state.generated = {}

# ── Sidebar branding ───────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding: 1.5rem 0 1rem;">
        <div style="font-size:2.8rem; margin-bottom:0.4rem;">
            <i class="fa-solid fa-book-open" style="color:#2dd4bf; filter: drop-shadow(0 0 8px rgba(45,212,191,0.4));"></i>
        </div>
        <h2 style="margin:0; font-size:1.15rem; color:#f1f5f9; font-weight:700; letter-spacing:0.02em;">核动力科研牛马</h2>
        <div style="font-size:0.75rem; color:#64748b; margin-top:6px; font-weight:500;">v0.2.0 · AI 驱动学术研究</div>
    </div>
    """, unsafe_allow_html=True)
    st.divider()

# ── Page definitions (using Font Awesome icons) ────────────
home      = st.Page("views/home_content.py",      title="首页",         icon="🏠")
agent_chat = st.Page("views/agent_chat.py",      title="智能体对话",   icon="💬")
workspace = st.Page("views/workspace_manager.py", title="工作空间",     icon="🗂️")
browser   = st.Page("views/topic_browser.py",     title="主题浏览",     icon="📂")
workbench = st.Page("views/reading_workbench.py", title="阅读工作台",   icon="📖")
memory    = st.Page("views/memory_panel.py",     title="记忆面板",     icon="🧠")
knowledge = st.Page("views/knowledge_base.py",   title="知识库",       icon="🗄️")
research  = st.Page("views/research_assistant.py",title="AI 研究助手",  icon="🔬")
obsidian  = st.Page("views/obsidian_panel.py",    title="Obsidian 面板",icon="📝")
dashboard = st.Page("views/reading_dashboard.py", title="阅读仪表盘",   icon="📊")
bill      = st.Page("views/llm_bill.py",          title="LLM 账单",     icon="💰")
oplog     = st.Page("views/operation_log.py",     title="操作日志",     icon="🕰️")
history   = st.Page("views/version_history.py",   title="版本回溯",     icon="📝")
graph     = st.Page("views/concept_graph.py",     title="概念图谱",     icon="🧩")
recommend = st.Page("views/recommend.py",         title="推荐",         icon="🎯")
skills    = st.Page("views/skill_manager.py",    title="技能管理",     icon="🧩")
rules     = st.Page("views/rule_editor.py",       title="规则设置",     icon="⚖️")
settings  = st.Page("views/settings.py",          title="设置",         icon="⚙️")
stats     = st.Page("views/stats.py",             title="统计",         icon="📈")

# ── Navigation ─────────────────────────────────────────────
pg = st.navigation(
    {
        "导航": [home, agent_chat, workspace, browser, workbench, memory, knowledge, research, obsidian, dashboard, bill, oplog, history, graph, recommend, skills, rules, settings, stats],
    },
    expanded=True,
)
pg.run()
