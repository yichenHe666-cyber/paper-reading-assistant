import time
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.cost_log import LLMCostLog
from app.models.llm_call import LLMCall
from app.config import get_settings


def get_today_cost(db: Session) -> float:
    today = str(date.today())
    result = db.query(func.coalesce(func.sum(LLMCostLog.cost_usd), 0.0)).filter(
        LLMCostLog.created_at.like(f"{today}%")
    ).scalar()
    return float(result)


def check_budget(db: Session, estimated_cost: float) -> bool:
    settings = get_settings()
    today_cost = get_today_cost(db)
    return (today_cost + estimated_cost) <= settings.daily_llm_budget_usd


def requires_approval(estimated_cost: float) -> bool:
    settings = get_settings()
    return estimated_cost > settings.require_approval_above_cost


def record_cost(
    db: Session,
    call_type: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    paper_id: str = None,
):
    log = LLMCostLog(
        call_type=call_type,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=_estimate_cost(prompt_tokens, completion_tokens, model),
        paper_id=paper_id,
    )
    db.add(log)
    db.commit()
    return log


def _estimate_cost(prompt_tokens: int, completion_tokens: int, model: str = None) -> float:
    settings = get_settings()
    model_name = (model or settings.llm_model).lower()

    # Per-token price table (USD per token; multiply by token count directly).
    # Values are taken from official provider pricing pages (per 1M tokens divided by 1M).
    price_table = {
        # OpenAI
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
        "gpt-4.1": (2.00, 8.00),
        "gpt-4.1-mini": (0.40, 1.60),
        "gpt-4.1-nano": (0.10, 0.40),
        "gpt-4-turbo": (10.00, 30.00),
        "gpt-3.5-turbo": (0.50, 1.50),
        "o1-mini": (3.00, 12.00),
        "o1": (15.00, 60.00),
        # Anthropic (OpenAI-compatible gateways)
        "claude-3-haiku": (0.25, 1.25),
        "claude-3-sonnet": (3.00, 15.00),
        "claude-3-opus": (15.00, 75.00),
        "claude-3-5-sonnet": (3.00, 15.00),
        "claude-3-5-haiku": (0.80, 4.00),
        # DeepSeek
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
        # Google Gemini (OpenAI-compatible endpoint)
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-1.5-pro": (1.25, 5.00),
        "gemini-2.0-flash": (0.10, 0.40),
        # xAI
        "grok-2": (2.00, 10.00),
        # Kimi / Moonshot
        "moonshot-v1-8k": (1.20, 1.20),
        # Conservative default rate for unknown models (USD per 1M tokens).
        "__default__": (1.00, 2.00),
    }

    def _lookup(name: str):
        if name in price_table:
            return price_table[name]
        for key, value in price_table.items():
            if key != "__default__" and key in name:
                return value
        return price_table["__default__"]

    input_rate, output_rate = _lookup(model_name)
    # Price table stores USD per 1M tokens (per official provider pricing
    # pages). Convert to per-token rate before multiplying by token count.
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return cost


def record_llm_call(
    db: Session,
    call_type: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    paper_id: str = None,
    duration_ms: int = 0,
):
    record_cost(db, call_type, model, prompt_tokens, completion_tokens, paper_id)
    call = LLMCall(
        call_type=call_type,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=_estimate_cost(prompt_tokens, completion_tokens, model),
        duration_ms=duration_ms,
        paper_id=paper_id,
    )
    db.add(call)
    db.commit()
    return call
