from pydantic_settings import BaseSettings
from functools import lru_cache
import os


class Settings(BaseSettings):
    database_path: str = "data/reading_assistant.db"
    obsidian_vault_path: str = "C:\\Users\\Public\\Documents"

    default_github_repo: str = "papers-we-love/papers-we-love"
    github_token: str = ""

    llm_provider: str = "DeepSeek"
    llm_api_base: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.3
    llm_timeout: float = 120.0
    # 思考强度: disabled(关闭) / high(标准) / max(最大深度)
    llm_reasoning_effort: str = "max"

    daily_llm_budget_usd: float = 3.0
    require_approval_above_cost: float = 0.10

    retriever: str = "duckduckgo"
    tavily_api_key: str = ""
    google_api_key: str = ""
    google_cx: str = ""
    bing_api_key: str = ""
    serper_api_key: str = ""
    exa_api_key: str = ""
    perplexity_api_key: str = ""
    search_max_retries: int = 3
    search_retry_base_delay: float = 2.0
    search_rate_limit_interval: float = 3.0
    search_fallback_chain: str = "duckduckgo,tavily,arxiv"

    api_key: str = ""

    api_port: int = 8000
    streamlit_port: int = 8501

    chat_default_context_max_tokens: int = 4096
    chat_default_context_strategy: str = "sliding_window"
    chat_default_skill_mode: str = "auto"
    chat_stream_enabled: bool = True
    chat_max_message_history: int = 1000
    sandbox_timeout_seconds: int = 30
    context_compress_threshold: float = 0.8

    embedding_provider: str = "auto"
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"

    memory_search_weights: str = "0.4,0.3,0.3"

    knowledge_base_path: str = "data/wiki-knowledge"
    knowledge_max_context_chars: int = 2000
    knowledge_enhanced_context_chars: int = 3000
    knowledge_extraction_max_tokens: int = 6000
    knowledge_graph_max_depth: int = 2
    knowledge_auto_extract: bool = True
    knowledge_dedup_enabled: bool = True

    log_level: str = "INFO"
    log_dir: str = "logs"
    log_file_max_bytes: int = 5242880
    log_file_backup_count: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
