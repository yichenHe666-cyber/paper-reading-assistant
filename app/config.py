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

    daily_llm_budget_usd: float = 3.0
    require_approval_above_cost: float = 0.10

    api_key: str = ""

    api_port: int = 8000
    streamlit_port: int = 8501

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
