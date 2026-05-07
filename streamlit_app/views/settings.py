import streamlit as st
from streamlit_app.utils.api_client import get, post, patch
from streamlit_app.components.icon import icon
from streamlit_app.components.card import card
import os

st.markdown(f"""
<div class="main-header">
    <h1>{icon('gear', size='lg')} 设置</h1>
    <p>管理核动力科研牛马的配置项</p>
</div>
""", unsafe_allow_html=True)

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")

# ── LLM Provider Presets ────────────────────────────────────
PROVIDER_PRESETS = {
    "OpenAI": {
        "base_url": "https://api.openai.com/v1",
        "models": [
            "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano",
            "o3-mini", "o1", "gpt-4o", "gpt-4o-mini",
        ],
    },
    "Google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": [
            "gemini-2.5-pro-preview-03-25", "gemini-2.5-flash-preview-04-17",
            "gemini-2.0-flash", "gemini-2.0-flash-lite",
        ],
    },
    "Anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            "claude-sonnet-4-20250514", "claude-opus-4-20250514",
            "claude-3-7-sonnet-20250219", "claude-3-5-haiku-20241022",
        ],
    },
    "xAI": {
        "base_url": "https://api.x.ai/v1",
        "models": [
            "grok-3", "grok-3-mini", "grok-2",
        ],
    },
    "DeepSeek": {
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            "deepseek-chat", "deepseek-reasoner", "deepseek-v4-pro", "deepseek-v3.1", "deepseek-r1",
        ],
    },
    "MiniMax Global": {
        "base_url": "https://api.minimaxi.com/v1",
        "models": [
            "minimax-text-01", "abab7-chat-preview", "abab6.5s-chat",
        ],
    },
    "Z.ai": {
        "base_url": "https://api.z.ai/v1",
        "models": [
            "z-ai-large", "z-ai-medium", "z-ai-small",
        ],
    },
    "Z.ai Plan": {
        "base_url": "https://api.z.ai/v1",
        "models": [
            "z-ai-pro", "z-ai-ultra",
        ],
    },
    "AWS": {
        "base_url": "https://bedrock-runtime.us-east-1.amazonaws.com",
        "models": [
            "anthropic.claude-sonnet-4-20250514-v1:0",
            "amazon.nova-pro-v1:0",
            "meta.llama3-3-70b-instruct-v1:0",
        ],
    },
    "OpenRouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "models": [
            "openrouter/auto",
            "anthropic/claude-sonnet-4",
            "google/gemini-2.5-pro-preview-03-25",
            "deepseek/deepseek-v3.1",
            "x-ai/grok-3",
        ],
    },
    "Kimi Global": {
        "base_url": "https://api.moonshot.cn/v1",
        "models": [
            "kimi-k2", "kimi-k2.5", "kimi-k1.5", "kimi-k1.5-long",
        ],
    },
}
PROVIDERS = list(PROVIDER_PRESETS.keys())
CUSTOM_MARKER = f"{icon('pen', size='sm')} 自定义输入..."

# ── Helpers ─────────────────────────────────────────────────

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "*" * len(key)
    return "[已配置] ***" + key[-4:]


def _read_env_value(key: str, default: str = "") -> str:
    env_path_local = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    key_upper = key.upper()
    if os.path.exists(env_path_local):
        with open(env_path_local, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key_upper}="):
                    return line[len(key_upper) + 1:].strip()
    return os.getenv(key_upper, default)


def _update_env(updates: dict):
    env_path_local = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
    lines = []
    if os.path.exists(env_path_local):
        with open(env_path_local, "r", encoding="utf-8") as f:
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

    with open(env_path_local, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ── Tabs ────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "🔑 LLM 配置",
    "📂 路径",
    "🪙 预算",
    "📚 订阅"
])

# ═════════════════════════════════════════════════════════════
# TAB 1: LLM 配置
# ═════════════════════════════════════════════════════════════
with tab1:
    st.subheader("🔑 LLM 模型配置")
    st.caption("选择模型服务商并配置调用参数，支持自定义模型名称与请求地址。")

    current_provider = _read_env_value("LLM_PROVIDER", "OpenAI")
    current_model = _read_env_value("LLM_MODEL", "")
    current_base = _read_env_value("LLM_API_BASE", "")
    current_key = _read_env_value("LLM_API_KEY", "")

    provider_idx = PROVIDERS.index(current_provider) if current_provider in PROVIDERS else 0
    provider = st.selectbox(
        "模型服务商",
        options=PROVIDERS,
        index=provider_idx,
        key="provider_select",
    )

    preset = PROVIDER_PRESETS.get(provider, {})
    default_models = preset.get("models", [])
    default_base = preset.get("base_url", "")

    known_bases = {p["base_url"] for p in PROVIDER_PRESETS.values()}
    if current_base in known_bases or not current_base:
        display_base = default_base
    else:
        display_base = current_base

    api_base = st.text_input(
        "自定义请求地址 (Base URL)",
        value=display_base,
        help="不同服务商的 API 入口地址。切换服务商时会自动填入默认值，你也可以手动修改。",
    )

    is_custom_model = current_model and current_model not in default_models

    model_options = (default_models or []) + [CUSTOM_MARKER]
    if is_custom_model:
        model_idx = len(default_models) if default_models else 0
    else:
        model_idx = default_models.index(current_model) if current_model in default_models else 0

    selected_model_option = st.selectbox(
        "模型",
        options=model_options,
        index=model_idx,
        help="选择推荐模型，或选「自定义输入」手动填写最新模型名称。",
    )

    if selected_model_option == CUSTOM_MARKER:
        custom_model = st.text_input(
            "自定义模型名称",
            value=current_model if is_custom_model else "",
            placeholder="例如：gpt-4.1-turbo-preview",
            help="输入任意模型 ID，服务商不认识时会返回错误。",
        )
        final_model = custom_model.strip()
    else:
        final_model = selected_model_option

    masked = _mask_key(current_key)
    api_key_input = st.text_input(
        "API 密钥",
        value=masked,
        type="password",
        help="留空表示不修改。输入新密钥后会覆盖旧密钥。密钥以加密形式存储在本地 .env 文件中。",
    )

    st.divider()
    st.subheader("🧠 思考强度")
    st.caption("控制模型的思考深度（仅 DeepSeek 等支持 thinking 模式的模型生效）")

    current_reasoning = _read_env_value("LLM_REASONING_EFFORT", "high")
    reasoning_options = {
        "disabled": "disabled — 关闭思考模式（响应最快，适合简单任务）",
        "high": "high — 标准思考深度（默认，平衡质量与速度）",
        "max": "max — 最大思考深度（适合复杂推理、数学证明、代码调试）",
    }
    reasoning_display = list(reasoning_options.values())
    reasoning_values = list(reasoning_options.keys())
    reasoning_idx = reasoning_values.index(current_reasoning) if current_reasoning in reasoning_values else 1

    selected_reasoning_display = st.selectbox(
        "思考强度",
        options=reasoning_display,
        index=reasoning_idx,
        help="disabled: 模型直接输出答案，不展示思维链\nhigh: 模型先思考再回答，适合大多数任务\nmax: 模型分配最大比例 token 用于推理，适合高难度任务",
    )
    selected_reasoning = reasoning_values[reasoning_display.index(selected_reasoning_display)]

    if st.button("💾 保存 LLM 配置", use_container_width=True, type="primary"):
        errors = []
        if not final_model:
            errors.append("请选择一个模型或输入自定义模型名称")
        if not api_base.strip():
            errors.append("请求地址不能为空")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                updates = {
                    "LLM_PROVIDER": provider,
                    "LLM_MODEL": final_model,
                    "LLM_API_BASE": api_base.strip(),
                    "LLM_REASONING_EFFORT": selected_reasoning,
                }
                if api_key_input != masked:
                    updates["LLM_API_KEY"] = api_key_input
                _update_env(updates)
                st.success("LLM 配置已保存，重启后端后生效")
                st.info(f"{icon('lightbulb', size='sm')} 提示：由于配置读取有缓存，请重新启动 FastAPI 服务（端口 8000）以应用新配置。")
            except Exception as e:
                st.error(f"保存失败: {e}")

# ═════════════════════════════════════════════════════════════
# TAB 2: 路径配置
# ═════════════════════════════════════════════════════════════
with tab2:
    st.subheader("📂 路径配置")
    current_vault = _read_env_value("OBSIDIAN_VAULT_PATH", r"C:\Users\Public\Documents")
    current_db = _read_env_value("DATABASE_PATH", "data/reading_assistant.db")

    vault = st.text_input("Obsidian Vault 路径", value=current_vault)
    db_path = st.text_input("数据库路径", value=current_db)

    if st.button("💾 保存路径配置", use_container_width=True, type="primary"):
        try:
            _update_env({"OBSIDIAN_VAULT_PATH": vault, "DATABASE_PATH": db_path})
            st.success("路径配置已保存，重启后生效")
        except Exception as e:
            st.error(f"保存失败: {e}")

# ═════════════════════════════════════════════════════════════
# TAB 3: 预算配置
# ═════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🪙 每日预算上限")
    current_budget = float(_read_env_value("DAILY_LLM_BUDGET_USD", "3.0"))
    current_threshold = float(_read_env_value("REQUIRE_APPROVAL_ABOVE_COST", "0.10"))

    budget = st.number_input("每日 LLM 预算上限 (USD)", min_value=0.1, max_value=100.0, value=current_budget, step=0.5)
    threshold = st.number_input("需人工确认的费用阈值 (USD)", min_value=0.01, max_value=10.0, value=current_threshold, step=0.01)

    st.caption("💡 当前设置：每天预算 ${current_budget}，单次超过 ${current_threshold} 需确认")

    if st.button("💾 保存预算配置", use_container_width=True, type="primary"):
        try:
            _update_env({
                "DAILY_LLM_BUDGET_USD": str(budget),
                "REQUIRE_APPROVAL_ABOVE_COST": str(threshold),
            })
            st.success("预算配置已保存，重启后生效")
        except Exception as e:
            st.error(f"保存失败: {e}")

    try:
        cost = get("/api/system/llm-cost")
        if cost:
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.metric("今日已花费", f"${cost.get('today_cost_usd', 0):.4f}")
            with col_c2:
                st.metric("本月已花费", f"${cost.get('monthly_cost_usd', 0):.4f}")
    except Exception:
        pass

# ═════════════════════════════════════════════════════════════
# TAB 4: 主题订阅
# ═════════════════════════════════════════════════════════════
with tab4:
    st.subheader("📖 主题订阅")
    st.caption("选择要同步的论文主题（全选=同步全部主题）")

    try:
        topics = get("/api/topics")
    except Exception:
        topics = []

    if topics:
        with st.expander("展开主题列表", expanded=True):
            subs = _read_env_value("TOPIC_SUBSCRIPTIONS", "")
            active = set(subs.split(",")) if subs else set()
            selected = []
            cols = st.columns(3)
            for i, t in enumerate(topics):
                with cols[i % 3]:
                    checked = t["id"] in active or not subs
                    if st.checkbox(
                        f"{t.get('name_cn', t['name'])}",
                        value=checked,
                        key=f"sub_{t['id']}",
                    ):
                        selected.append(t["id"])

            if st.button("💾 保存订阅", use_container_width=True, type="primary"):
                try:
                    _update_env({"TOPIC_SUBSCRIPTIONS": ",".join(selected)})
                    st.success(f"已订阅 {len(selected)} 个主题，重启后生效")
                except Exception as e:
                    st.error(f"保存失败: {e}")
    else:
        empty_state(title="暂无主题", description="暂无主题数据，请先同步论文库", icon_name="book")
