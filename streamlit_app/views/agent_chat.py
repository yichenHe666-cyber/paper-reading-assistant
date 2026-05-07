import streamlit as st
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit_app.utils.api_client import get, post, patch, delete as api_delete

_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

PROVIDER_PRESETS = {
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3-mini", "o1", "gpt-4o", "gpt-4o-mini"],
    },
    "Google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": ["gemini-2.5-pro-preview-03-25", "gemini-2.5-flash-preview-04-17", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
    },
    "Anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514", "claude-3-7-sonnet-20250219", "claude-3-5-haiku-20241022"],
    },
    "xAI": {
        "base_url": "https://api.x.ai/v1",
        "models": ["grok-3", "grok-3-mini", "grok-2"],
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro", "deepseek-v3.1", "deepseek-r1"],
    },
    "MiniMax Global": {
        "base_url": "https://api.minimaxi.com/v1",
        "models": ["minimax-text-01", "abab7-chat-preview", "abab6.5s-chat"],
    },
    "Z.ai": {
        "base_url": "https://api.z.ai/v1",
        "models": ["z-ai-large", "z-ai-medium", "z-ai-small"],
    },
    "Z.ai Plan": {
        "base_url": "https://api.z.ai/v1",
        "models": ["z-ai-pro", "z-ai-ultra"],
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openrouter/auto", "anthropic/claude-sonnet-4", "google/gemini-2.5-pro-preview-03-25", "deepseek/deepseek-v3.1", "x-ai/grok-3"],
    },
    "Kimi Global": {
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["kimi-k2", "kimi-k2.5", "kimi-k1.5", "kimi-k1.5-long"],
    },
}

def _read_env_value(key: str, default: str = "") -> str:
    key_upper = key.upper()
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key_upper}="):
                    return line[len(key_upper) + 1:].strip()
    return os.getenv(key_upper, default)

def _update_env(updates: dict):
    lines = []
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    for key, value in updates.items():
        key_upper = key.upper()
        found = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key_upper}=") or line.strip().startswith(f"# {key_upper}="):
                lines[i] = f"{key_upper}={value}\n"
                found = True
                break
        if not found:
            lines.append(f"{key_upper}={value}\n")
    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None
if "chat_messages_cache" not in st.session_state:
    st.session_state.chat_messages_cache = {}
if "input_text" not in st.session_state:
    st.session_state.input_text = ""
if "skill_preset" not in st.session_state:
    st.session_state.skill_preset = ""
if "selected_skill_preset" not in st.session_state:
    st.session_state.selected_skill_preset = None
if "skill_preset_toast" not in st.session_state:
    st.session_state.skill_preset_toast = ""

def _load_sessions():
    try:
        data = get("/api/chat/sessions?limit=100")
        return data.get("sessions", [])
    except Exception:
        return []

def _load_messages(session_id):
    try:
        data = get(f"/api/chat/sessions/{session_id}")
        return data.get("messages", [])
    except Exception:
        return []

def _create_session():
    result = post("/api/chat/sessions", {"title": "新对话"})
    if "id" in result:
        st.session_state.current_session_id = result["id"]
        st.rerun()

def _send_message(session_id, content):
    result = post(f"/api/chat/sessions/{session_id}/messages", {"content": content})
    return result

def _delete_session(session_id):
    try:
        api_delete(f"/api/chat/sessions/{session_id}")
        if st.session_state.current_session_id == session_id:
            st.session_state.current_session_id = None
        st.rerun()
    except Exception:
        pass

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .block-container { padding: 0 !important; max-width: 100% !important; }
    .doubao-layout {
        display: flex;
        height: 100vh;
        width: 100%;
        background: rgba(11,17,32,0.98);
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    .doubao-sidebar {
        width: 240px; min-width: 240px;
        background: rgba(15,23,42,0.85);
        border-right: 1px solid rgba(255,255,255,0.06);
        display: flex; flex-direction: column;
        padding: 16px; box-sizing: border-box;
    }
    .doubao-new-chat-btn {
        background: #2dd4bf; color: #0B1120; border: none;
        border-radius: 8px; padding: 10px 16px; font-size: 14px;
        font-weight: 600; cursor: pointer; width: 100%;
        margin-bottom: 12px; display: flex; align-items: center;
        justify-content: center; gap: 6px; transition: all 0.2s;
    }
    .doubao-new-chat-btn:hover { background: #14b8a6; transform: translateY(-1px); }
    .doubao-search-box {
        background: rgba(255,255,255,0.06); border: none;
        border-radius: 8px; padding: 8px 12px; font-size: 13px;
        width: 100%; box-sizing: border-box; margin-bottom: 12px;
        outline: none; color: #f1f5f9;
    }
    .doubao-search-box:focus { background: rgba(255,255,255,0.10); border: 1px solid rgba(45,212,191,0.3); }
    .doubao-search-box::placeholder { color: #64748b; }
    .doubao-session-list { flex: 1; overflow-y: auto; }
    .doubao-session-item {
        padding: 10px 12px; border-radius: 8px; cursor: pointer;
        font-size: 13px; color: #94a3b8; margin-bottom: 2px;
        position: relative; display: flex; align-items: center;
        justify-content: space-between; transition: background 0.15s;
    }
    .doubao-session-item:hover { background: rgba(255,255,255,0.08); color: #f1f5f9; }
    .doubao-session-item.active { background: rgba(45,212,191,0.1); color: #f1f5f9; }
    .doubao-session-item.active::before {
        content: ""; position: absolute; left: 0; top: 50%;
        transform: translateY(-50%); width: 3px; height: 16px;
        background: #2dd4bf; border-radius: 0 2px 2px 0;
    }
    .doubao-session-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
    .doubao-session-delete {
        opacity: 0; color: #64748b; font-size: 12px; padding: 2px 6px;
        border-radius: 4px; transition: opacity 0.15s, background 0.15s;
    }
    .doubao-session-item:hover .doubao-session-delete { opacity: 1; }
    .doubao-session-delete:hover { background: rgba(248,113,113,0.2); color: #f87171; }

    .doubao-chat-area {
        flex: 1; display: flex; flex-direction: column;
        min-width: 0; background: rgba(11,17,32,0.95);
    }
    .doubao-chat-header {
        height: 44px; border-bottom: 1px solid rgba(255,255,255,0.06);
        display: flex; align-items: center; justify-content: center;
        padding: 0 24px; flex-shrink: 0; backdrop-filter: blur(10px);
    }
    .doubao-chat-header-title { font-size: 15px; font-weight: 600; color: #f1f5f9; }
    .doubao-chat-messages {
        flex: 1; overflow-y: auto; padding: 16px 24px;
        display: flex; flex-direction: column;
    }
    .doubao-empty-state {
        flex: 1; display: flex; flex-direction: column;
        align-items: center; justify-content: center; padding: 16px 24px;
    }
    .doubao-empty-title { font-size: 24px; font-weight: 600; color: #f1f5f9; margin-bottom: 24px; }
    .doubao-pill-container {
        display: flex; flex-wrap: wrap; gap: 10px;
        justify-content: center; max-width: 720px;
    }
    .doubao-pill {
        background: rgba(255,255,255,0.03); color: #94a3b8;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px; padding: 12px 20px; font-size: 13px;
        cursor: pointer; transition: all 0.15s; white-space: nowrap;
        line-height: 1.4;
    }
    .doubao-pill:hover { background: rgba(255,255,255,0.07); color: #f1f5f9; border-color: rgba(45,212,191,0.2); }
    .doubao-message-row { display: flex; margin-bottom: 16px; max-width: 100%; }
    .doubao-message-row.user { justify-content: flex-end; }
    .doubao-message-row.assistant { justify-content: flex-start; }
    .doubao-message-bubble {
        max-width: 70%; padding: 12px 16px; font-size: 14px;
        line-height: 1.6; word-wrap: break-word;
    }
    .doubao-message-bubble.user {
        background: linear-gradient(135deg, #2dd4bf, #14b8a6); color: #0B1120;
        border-radius: 12px 12px 4px 12px;
    }
    .doubao-message-bubble.assistant {
        background: rgba(255,255,255,0.04); color: #f1f5f9;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 4px 12px 12px 12px;
    }
    .doubao-message-avatar {
        width: 32px; height: 32px; border-radius: 50%;
        background: linear-gradient(135deg, #2dd4bf, #14b8a6);
        color: #0B1120; display: flex; align-items: center;
        justify-content: center; font-size: 13px; font-weight: 700;
        margin-right: 8px; flex-shrink: 0;
    }
    .doubao-typing { display: flex; align-items: center; gap: 4px; padding: 12px 16px; }
    .doubao-typing-dot {
        width: 8px; height: 8px; background: #2dd4bf; border-radius: 50%;
        animation: doubao-bounce 1.4s infinite ease-in-out both;
    }
    .doubao-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .doubao-typing-dot:nth-child(2) { animation-delay: -0.16s; }
    @keyframes doubao-bounce { 0%,80%,100%{transform:scale(0);} 40%{transform:scale(1);} }

    .doubao-input-area {
        border-top: 1px solid rgba(255,255,255,0.06);
        padding: 16px 24px 20px; flex-shrink: 0;
        background: rgba(11,17,32,0.98);
    }
    .doubao-input-wrapper {
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 12px 16px 8px;
        display: flex;
        flex-direction: column;
        gap: 4px;
        transition: all 0.2s ease;
    }
    .doubao-input-wrapper:focus-within {
        border-color: rgba(45,212,191,0.3);
        background: rgba(255,255,255,0.06);
    }
    .doubao-skill-container {
        border-radius: 12px;
        border: 1px solid rgba(255,255,255,0.08);
        background: rgba(255,255,255,0.04);
        padding: 8px 12px;
        margin-bottom: 8px;
    }
    .doubao-skill-divider-line {
        height: 1px;
        background: rgba(255,255,255,0.06);
        margin: 4px 0;
    }

    .doubao-skill-toast {
        background: rgba(45,212,191,0.12);
        color: #2dd4bf;
        border-radius: 8px;
        padding: 6px 14px;
        font-size: 12px;
        text-align: center;
        margin-bottom: 8px;
        animation: doubao-toast-in 0.15s ease;
    }
    .doubao-skill-toast.fade-out {
        animation: doubao-toast-out 0.3s ease forwards;
    }
    @keyframes doubao-toast-in { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes doubao-toast-out { from { opacity: 1; transform: translateY(0); } to { opacity: 0; transform: translateY(-4px); } }

    .doubao-input-row {
        display: flex;
        align-items: flex-end;
        gap: 8px;
    }
    .doubao-input-field {
        flex: 1;
        border: none;
        background: transparent;
        font-size: 14px;
        line-height: 1.5;
        resize: none;
        outline: none;
        max-height: 120px;
        min-height: 24px;
        padding: 4px 0;
        color: #f1f5f9;
    }
    .doubao-input-field::placeholder { color: #64748b; }
    .doubao-send-btn {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        background: linear-gradient(135deg, #2dd4bf, #14b8a6);
        color: #0B1120;
        border: none;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        flex-shrink: 0;
        transition: all 0.2s;
        font-size: 16px;
        font-weight: bold;
    }
    .doubao-send-btn:hover { transform: scale(1.05); box-shadow: 0 0 20px rgba(45,212,191,0.3); }
    .doubao-send-btn:disabled { background: rgba(255,255,255,0.1); cursor: not-allowed; }

    .doubao-right-panel {
        width: 280px; min-width: 280px;
        background: rgba(15,23,42,0.85);
        border-left: 1px solid rgba(255,255,255,0.06);
        padding: 20px; box-sizing: border-box; overflow-y: auto;
    }
    .doubao-panel-section {
        margin-bottom: 12px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.06);
        background: rgba(255,255,255,0.02);
        padding: 12px;
    }
    .doubao-panel-title {
        font-size: 14px; font-weight: 600; color: #f1f5f9;
        margin-bottom: 10px; letter-spacing: 0.02em;
        text-align: center;
    }
    .doubao-progress-bg {
        background: rgba(255,255,255,0.08); border-radius: 6px;
        height: 8px; overflow: hidden;
    }
    .doubao-progress-fill { height: 100%; border-radius: 6px; transition: width 0.3s; }
    .doubao-progress-text { font-size: 12px; color: #64748b; margin-top: 6px; text-align: center; }
    .doubao-info-row {
        font-size: 13px; color: #94a3b8; margin-bottom: 6px;
        display: flex; align-items: center; justify-content: space-between;
        gap: 6px;
    }
    .doubao-info-label { color: #64748b; }
    .doubao-right-panel .stSelectbox { margin-bottom: 4px !important; }
    .doubao-right-panel .stSelectbox > div > div { padding: 2px 0 !important; }
    .doubao-right-panel .stSelectbox label { font-size: 12px !important; color: #94a3b8 !important; margin-bottom: 2px !important; }
    .doubao-cmd-item {
        font-size: 12px; padding: 8px 10px; border-radius: 8px;
        background: rgba(255,255,255,0.03); margin-bottom: 6px;
        cursor: pointer; transition: background 0.15s;
        display: flex; align-items: center; gap: 8px;
        border: 1px solid transparent;
    }
    .doubao-cmd-item:hover { background: rgba(255,255,255,0.08); border-color: rgba(45,212,191,0.2); }
    .doubao-cmd-code {
        font-family: "SF Mono", Monaco, monospace;
        color: #2dd4bf; font-weight: 500; font-size: 11px;
        background: rgba(45,212,191,0.1); padding: 2px 6px; border-radius: 4px;
    }
    .doubao-cmd-desc { color: #64748b; }
    .doubao-compress-btn {
        background: rgba(255,255,255,0.05); color: #94a3b8;
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px; padding: 10px 12px; font-size: 12px;
        cursor: pointer; width: 100%; transition: all 0.15s; margin-top: 8px;
    }
    .doubao-compress-btn:hover { background: rgba(255,255,255,0.10); color: #f1f5f9; }
    .doubao-reasoning-box {
        background: rgba(255,255,255,0.02);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
        font-size: 12px; color: #94a3b8; line-height: 1.6;
        max-height: 300px; overflow-y: auto; white-space: pre-wrap;
    }
    .doubao-reasoning-toggle {
        font-size: 12px; color: #2dd4bf; cursor: pointer;
        margin-bottom: 8px; display: inline-flex; align-items: center; gap: 4px;
    }
    .doubao-model-badge { font-size: 11px; color: #64748b; margin-top: 4px; }
    .doubao-system-msg {
        text-align: center; margin: 8px 0; font-size: 12px;
        color: #64748b; font-style: italic;
    }
    .doubao-function-box {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: 12px;
    }
    .doubao-function-title { font-weight: 600; color: #94a3b8; margin-bottom: 4px; display: flex; align-items: center; gap: 4px; }

    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }

    button[kind="secondary"] {
        background: transparent !important;
        border: none !important;
        color: #94a3b8 !important;
        border-radius: 8px !important;
        font-size: 12px !important;
        transition: all 0.15s ease !important;
    }
    button[kind="secondary"]:hover {
        background: rgba(255,255,255,0.08) !important;
        color: #f1f5f9 !important;
    }

    [data-testid="stChatInput"] {
        background: transparent !important;
        border: none !important;
        padding: 0 !important;
    }
    [data-testid="stChatInput"] > div {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }
    [data-testid="stChatInputTextArea"] {
        background: transparent !important;
        color: #f1f5f9 !important;
        border: none !important;
        caret-color: #2dd4bf !important;
    }
    [data-testid="stChatInputTextArea"]::placeholder {
        color: #64748b !important;
    }
    [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"] {
        background: linear-gradient(135deg, #2dd4bf, #14b8a6) !important;
        border-radius: 50% !important;
        color: #0B1120 !important;
        border: none !important;
    }
    [data-testid="stChatInput"] button[data-testid="stChatInputSubmitButton"]:hover {
        box-shadow: 0 0 20px rgba(45,212,191,0.3) !important;
    }
</style>
""", unsafe_allow_html=True)

sessions = _load_sessions()
current_session_id = st.session_state.current_session_id
session_data = None
messages = []
if current_session_id:
    try:
        session_data = get(f"/api/chat/sessions/{current_session_id}")
        if session_data and "id" in session_data:
            messages = session_data.get("messages", [])
        else:
            session_data = None
            current_session_id = None
            st.session_state.current_session_id = None
    except Exception:
        session_data = None

col_sidebar, col_main, col_right = st.columns([0.7, 3, 0.85])

with col_sidebar:
    if st.button("➕ 新对话", key="new_chat_btn_main", use_container_width=True):
        _create_session()

    for idx, s in enumerate(sessions):
        is_active = s["id"] == current_session_id
        raw_title = s.get("title", "") or "新对话"
        title = raw_title[:28]
        msg_count = s.get("message_count", 0)
        display_title = f"{title}" if raw_title != "新对话" else f"新对话 #{idx+1}"
        if is_active:
            st.button(f"📌 {display_title}", key=f"sess_{s['id']}", use_container_width=True,
                       help="当前对话", disabled=True)
        else:
            if st.button(f"💬 {display_title}", key=f"sess_{s['id']}", use_container_width=True):
                st.session_state.current_session_id = s["id"]
                st.rerun()

    if not sessions:
        st.caption("暂无历史对话")

with col_main:
    chat_title = (session_data.get("title", "智能体对话") if session_data else "智能体对话")
    st.markdown(f"""
    <div style="text-align:center;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.06);">
        <span style="font-size:15px;font-weight:600;color:#f1f5f9;">{chat_title}</span>
    </div>
    """, unsafe_allow_html=True)

    if not current_session_id:
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;">
            <div style="font-size:20px;font-weight:700;color:#f1f5f9;margin-bottom:12px;">有什么我能帮你的吗？</div>
            <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:650px;">
                <span class="doubao-pill">帮我写一份项目计划书</span>
                <span class="doubao-pill">解释量子计算基本原理</span>
                <span class="doubao-pill">生成Python爬虫示例</span>
                <span class="doubao-pill">分析最近市场趋势</span>
                <span class="doubao-pill">帮我优化这段代码</span>
                <span class="doubao-pill">写一篇AI科普文章</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    elif messages:
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            reasoning_content = msg.get("reasoning_content", "") or ""
            model_used = msg.get("model_used", "")

            if role == "user":
                st.markdown(f"""
                <div style="display:flex;justify-content:flex-end;margin-bottom:16px;">
                    <div class="doubao-message-bubble user">{content}</div>
                </div>
                """, unsafe_allow_html=True)
            elif role == "assistant":
                reasoning_html = ""
                if reasoning_content and reasoning_content.strip():
                    reasoning_html = f"""
                    <div style="margin-bottom:4px;">
                        <span class="doubao-reasoning-toggle" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
                            💭 思考过程 ▼
                        </span>
                        <div class="doubao-reasoning-box" style="display:none;">{reasoning_content}</div>
                    </div>
                    """
                model_badge = f'<div class="doubao-model-badge">{model_used}</div>' if model_used else ''
                st.markdown(f"""
                <div style="display:flex;justify-content:flex-start;margin-bottom:16px;">
                    <div class="doubao-message-avatar">AI</div>
                    <div>{reasoning_html}<div class="doubao-message-bubble assistant">{content}</div>{model_badge}</div>
                </div>
                """, unsafe_allow_html=True)
            elif role == "system":
                st.markdown(f'<div class="doubao-system-msg">{content}</div>', unsafe_allow_html=True)
            elif role == "function_call":
                st.markdown(f"""
                <div class="doubao-function-box">
                    <div class="doubao-function-title">🔧 技能调用</div>
                    <div style="color:#94a3b8;font-size:12px;white-space:pre-wrap;">{content[:500]}</div>
                </div>
                """, unsafe_allow_html=True)
            elif role == "function_result":
                st.markdown(f"""
                <div class="doubao-function-box">
                    <div class="doubao-function-title">📋 技能结果</div>
                    <div style="color:#94a3b8;font-size:12px;white-space:pre-wrap;">{content[:500]}</div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("""
        <script>document.querySelector('.doubao-chat-messages')?.scrollTo(0,99999)</script>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:16px;">
            <div style="font-size:20px;font-weight:600;color:#f1f5f9;margin-bottom:8px;">开始对话</div>
            <div style="color:#64748b;font-size:14px;">在下方输入消息开始与智能体对话</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div class="doubao-input-area">', unsafe_allow_html=True)

    SKILL_PRESETS = [
        ("⚡ 快速回答", "快速回答：", "快速回答"),
        ("📊 PPT生成", "请帮我生成一份PPT大纲，主题是：", "PPT生成"),
        ("💻 编程", "请帮我编写代码，需求是：", "编程"),
        ("✍️ 帮我写作", "请帮我写一篇文章，主题是：", "帮我写作"),
        ("🎨 图片生成", "请帮我生成图片，描述是：", "图片生成"),
        ("🔬 深入研究", "请深入研究以下主题：", "深入研究"),
    ]

    selected_idx = st.session_state.get("selected_skill_preset")

    if selected_idx is not None and 0 <= selected_idx < len(SKILL_PRESETS):
        toast_text = st.session_state.get("skill_preset_toast", "")
        if toast_text:
            st.markdown(f'<div class="doubao-skill-toast">{toast_text}</div>', unsafe_allow_html=True)

    st.markdown('<div class="doubao-input-wrapper">', unsafe_allow_html=True)

    st.markdown('<div class="doubao-skill-container">', unsafe_allow_html=True)
    skill_cols = st.columns(len(SKILL_PRESETS))
    for idx, (label, preset_val, toast_name) in enumerate(SKILL_PRESETS):
        is_active = selected_idx == idx
        with skill_cols[idx]:
            if st.button(label, key=f"skill_{idx}", use_container_width=True):
                if is_active:
                    st.session_state.selected_skill_preset = None
                    st.session_state.skill_preset = ""
                    st.session_state.skill_preset_toast = ""
                else:
                    st.session_state.selected_skill_preset = idx
                    st.session_state.skill_preset = preset_val
                    st.session_state.skill_preset_toast = f"已切换至【{toast_name}】模式"
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    active_idx = st.session_state.get("selected_skill_preset")
    if active_idx is not None:
        st.markdown(f"""
    <style>
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"]:nth-of-type({active_idx + 1}) button[kind="secondary"] {{
        background: rgba(45,212,191,0.15) !important;
        color: #2dd4bf !important;
        border: none !important;
        border-bottom: 2px solid #2dd4bf !important;
        border-radius: 8px !important;
        transition: all 0.15s ease !important;
    }}
    [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"]:nth-of-type({active_idx + 1}) button[kind="secondary"]:hover {{
        background: rgba(45,212,191,0.20) !important;
    }}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="doubao-skill-divider-line"></div>', unsafe_allow_html=True)

    preset = st.session_state.get("skill_preset", "")
    placeholder_text = preset if preset else "输入消息（/ 开头为指令）..."
    user_input = st.chat_input(placeholder_text, key="main_chat_input")
    if user_input:
        full_msg = preset + user_input if preset else user_input
        st.session_state.skill_preset = ""
        st.session_state.selected_skill_preset = None
        st.session_state.skill_preset_toast = ""
        if current_session_id:
            _send_message(current_session_id, full_msg)
            st.rerun()
        else:
            _create_session()
            if st.session_state.current_session_id:
                _send_message(st.session_state.current_session_id, full_msg)
                st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    import streamlit.components.v1 as components
    components.html("""
<script>
(function() {
    var doc = window.parent.document;
    var COMMANDS = [
        { cmd: '/plan', desc: '任务规划 — 生成结构化任务计划' },
        { cmd: '/spec', desc: '需求规格 — 编写详细需求文档' },
        { cmd: '/compress', desc: '压缩上下文 — 压缩对话历史节省 token' },
        { cmd: '/memory', desc: '查看记忆 — 显示智能体记忆内容' },
        { cmd: '/rules', desc: '查看规则 — 显示当前项目规则' },
        { cmd: '/help', desc: '帮助 — 显示所有可用命令' },
        { cmd: '/search', desc: '搜索 — 联网搜索信息' },
        { cmd: '/reset', desc: '重置 — 清空当前对话' }
    ];
    var panel = null;
    var selectedIndex = -1;
    var filteredCmds = [];

    function findChatTextarea() {
        return doc.querySelector('[data-testid="stChatInputTextArea"]');
    }

    function createPanel() {
        if (panel) return panel;
        panel = doc.createElement('div');
        panel.id = 'cmd-autocomplete-panel';
        panel.style.cssText = 'position:fixed;bottom:120px;left:50%;transform:translateX(-50%);' +
            'width:420px;max-height:320px;overflow-y:auto;' +
            'background:rgba(15,23,42,0.97);border:1px solid rgba(45,212,191,0.25);' +
            'border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,0.5);' +
            'z-index:99999;display:none;padding:8px;' +
            'font-family:-apple-system,BlinkMacSystemFont,sans-serif;';
        doc.body.appendChild(panel);
        return panel;
    }

    function showPanel(query) {
        var p = createPanel();
        filteredCmds = COMMANDS.filter(function(c) {
            return c.cmd.startsWith(query.toLowerCase()) || c.desc.toLowerCase().includes(query.toLowerCase().slice(1));
        });
        if (filteredCmds.length === 0) { p.style.display = 'none'; return; }
        selectedIndex = -1;
        var html = '<div style="padding:6px 10px;font-size:11px;color:#64748b;border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:4px;">命令提示</div>';
        filteredCmds.forEach(function(c, i) {
            html += '<div class="cmd-item" data-index="' + i + '" style="' +
                'padding:10px 14px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:10px;' +
                'transition:background 0.1s;margin-bottom:2px;">' +
                '<span style="font-family:SF Mono,Monaco,monospace;color:#2dd4bf;font-weight:600;font-size:13px;' +
                'background:rgba(45,212,191,0.1);padding:2px 8px;border-radius:4px;min-width:80px;text-align:center;">' + c.cmd + '</span>' +
                '<span style="color:#94a3b8;font-size:12px;">' + c.desc + '</span>' +
                '</div>';
        });
        p.innerHTML = html;
        p.style.display = 'block';
        p.querySelectorAll('.cmd-item').forEach(function(el) {
            el.addEventListener('mouseenter', function() {
                clearHighlight();
                selectedIndex = parseInt(el.dataset.index);
                el.style.background = 'rgba(45,212,191,0.1)';
            });
            el.addEventListener('mouseleave', function() {
                el.style.background = 'transparent';
            });
            el.addEventListener('click', function() {
                selectCommand(parseInt(el.dataset.index));
            });
        });
    }

    function clearHighlight() {
        if (!panel) return;
        panel.querySelectorAll('.cmd-item').forEach(function(el) {
            el.style.background = 'transparent';
        });
    }

    function highlightItem(index) {
        if (!panel || filteredCmds.length === 0) return;
        clearHighlight();
        selectedIndex = index;
        if (selectedIndex < 0) selectedIndex = filteredCmds.length - 1;
        if (selectedIndex >= filteredCmds.length) selectedIndex = 0;
        var items = panel.querySelectorAll('.cmd-item');
        if (items[selectedIndex]) {
            items[selectedIndex].style.background = 'rgba(45,212,191,0.15)';
            items[selectedIndex].scrollIntoView({ block: 'nearest' });
        }
    }

    function selectCommand(index) {
        if (index < 0 || index >= filteredCmds.length) return;
        var cmd = filteredCmds[index].cmd;
        var textarea = findChatTextarea();
        if (textarea) {
            var val = textarea.value;
            var slashIdx = val.lastIndexOf('/');
            if (slashIdx >= 0) {
                textarea.value = val.substring(0, slashIdx) + cmd + ' ';
            } else {
                textarea.value = cmd + ' ';
            }
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            textarea.focus();
        }
        hidePanel();
    }

    function hidePanel() {
        if (panel) panel.style.display = 'none';
        selectedIndex = -1;
        filteredCmds = [];
    }

    function setup() {
        var textarea = findChatTextarea();
        if (!textarea) { setTimeout(setup, 500); return; }

        textarea.addEventListener('input', function() {
            var val = textarea.value;
            var slashIdx = val.lastIndexOf('/');
            if (slashIdx >= 0) {
                var afterSlash = val.substring(slashIdx);
                if (!afterSlash.includes(' ') && afterSlash.length <= 15) {
                    showPanel(afterSlash);
                    return;
                }
            }
            hidePanel();
        });

        textarea.addEventListener('keydown', function(e) {
            if (!panel || panel.style.display === 'none') return;
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                highlightItem(selectedIndex + 1);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                highlightItem(selectedIndex - 1);
            } else if (e.key === 'Enter' && selectedIndex >= 0) {
                e.preventDefault();
                selectCommand(selectedIndex);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                hidePanel();
            } else if (e.key === 'Tab' && selectedIndex >= 0) {
                e.preventDefault();
                selectCommand(selectedIndex);
            }
        });

        doc.addEventListener('click', function(e) {
            if (panel && !panel.contains(e.target) && e.target !== textarea) {
                hidePanel();
            }
        });
    }

    if (doc.readyState === 'loading') {
        doc.addEventListener('DOMContentLoaded', function() { setTimeout(setup, 300); });
    } else {
        setTimeout(setup, 300);
    }
})();
</script>
""", height=0)

with col_right:
    if current_session_id and session_data:
        try:
            usage = get(f"/api/chat/sessions/{current_session_id}/context-usage")
            if usage and "usage_pct" in usage:
                pct = usage["usage_pct"]
                level_color = "#2dd4bf" if pct < 60 else "#fbbf24" if pct < 80 else "#f87171"
                st.markdown(f"""
                <div class="doubao-panel-section">
                    <div class="doubao-panel-title">上下文使用率</div>
                    <div class="doubao-progress-bg">
                        <div class="doubao-progress-fill" style="background:{level_color};width:{min(pct,100)}%;"></div>
                    </div>
                    <div class="doubao-progress-text">{pct:.1f}% ({usage.get('total_tokens',0)} tokens)</div>
                </div>
                """, unsafe_allow_html=True)
        except Exception:
            pass
    else:
        st.markdown("""
        <div style="text-align:center;padding:24px 0;color:#64748b;font-size:13px;">
            <div style="font-size:36px;margin-bottom:12px;">💬</div>
            <div>请先选择一个对话</div>
        </div>
        """, unsafe_allow_html=True)

    current_model_display = session_data.get('model_name', _read_env_value("LLM_DEFAULT_MODEL", "deepseek-chat")) if session_data else _read_env_value("LLM_DEFAULT_MODEL", "deepseek-chat")
    current_reasoning = _read_env_value("LLM_REASONING_EFFORT", "high")
    reasoning_labels = {"disabled": "关闭", "high": "标准", "max": "最大深度"}
    current_provider = _read_env_value("LLM_PROVIDER", "DeepSeek")
    provider_models = PROVIDER_PRESETS.get(current_provider, {}).get("models", [current_model_display])
    all_models = provider_models if current_model_display in provider_models else [current_model_display] + provider_models

    st.markdown(f"""
    <div class="doubao-panel-section">
        <div class="doubao-panel-title">模型设置</div>
        <div class="doubao-info-row">
            <span class="doubao-info-label">当前模型</span>
            <span style="color:#2dd4bf;font-weight:600;">{current_model_display}</span>
        </div>
        <div class="doubao-info-row">
            <span class="doubao-info-label">思考强度</span>
            <span style="background:rgba(45,212,191,0.15);color:#2dd4bf;padding:2px 8px;border-radius:4px;font-size:11px;">{reasoning_labels.get(current_reasoning, current_reasoning)}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    model_idx = all_models.index(current_model_display) if current_model_display in all_models else 0
    selected_model = st.selectbox(
        "切换模型",
        options=all_models,
        index=model_idx,
        key="chat_model_switch",
    )
    if selected_model != current_model_display:
        if current_session_id:
            try:
                patch(f"/api/chat/sessions/{current_session_id}", {"model_name": selected_model})
            except Exception:
                pass
        _update_env({"LLM_DEFAULT_MODEL": selected_model})
        st.toast(f"模型已切换至 {selected_model}", icon="🔄")
        st.rerun()

    reasoning_options = ["disabled", "high", "max"]
    reasoning_idx = reasoning_options.index(current_reasoning) if current_reasoning in reasoning_options else 1
    selected_reasoning = st.selectbox(
        "思考强度",
        options=reasoning_options,
        index=reasoning_idx,
        format_func=lambda x: f"{reasoning_labels.get(x, x)}",
        key="chat_reasoning_switch",
    )
    if selected_reasoning != current_reasoning:
        _update_env({"LLM_REASONING_EFFORT": selected_reasoning})
        st.toast(f"思考强度已调整为 {reasoning_labels.get(selected_reasoning, selected_reasoning)}", icon="🧠")
        st.rerun()

    if current_session_id and session_data:
        st.markdown(f"""
        <div class="doubao-panel-section">
            <div class="doubao-panel-title">会话信息</div>
            <div class="doubao-info-row"><span class="doubao-info-label">技能模式</span><span>{session_data.get('skill_mode','auto')}</span></div>
            <div class="doubao-info-row"><span class="doubao-info-label">Token</span><span>{session_data.get('total_tokens',0)}</span></div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("""<div class="doubao-panel-section"><div class="doubao-panel-title">快捷指令</div>""", unsafe_allow_html=True)
        cmds = [("/plan","任务规划"),("/spec","需求规格"), ("/compress","压缩上下文"), ("/memory","查看记忆"), ("/rules","查看规则"), ("/help","帮助")]
        for cmd, desc in cmds:
            if st.button(f"`{cmd}`  {desc}", key=f"cmd_{cmd.replace('/','_')}"):
                if current_session_id:
                    _send_message(current_session_id, cmd)
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        if st.button("📦 压缩上下文", use_container_width=True, key="compress_btn"):
            try:
                result = post(f"/api/chat/sessions/{current_session_id}/compress", {})
                if "error" not in result:
                    st.success("上下文已压缩 ✅")
                    st.rerun()
            except Exception:
                st.error("压缩失败")
