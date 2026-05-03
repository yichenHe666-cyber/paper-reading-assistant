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
        cost_usd=_estimate_cost(prompt_tokens, completion_tokens),
        paper_id=paper_id,
    )
    db.add(log)
    db.commit()
    return log


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    settings = get_settings()
    model = settings.llm_model.lower()
    if "gpt-4o-mini" in model:
        return (prompt_tokens * 0.15 + completion_tokens * 0.60) / 1_000_000
    elif "gpt-4o" in model:
        return (prompt_tokens * 2.50 + completion_tokens * 10.00) / 1_000_000
    elif "claude" in model:
        return (prompt_tokens * 0.80 + completion_tokens * 4.00) / 1_000_000
    return 0.0


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
        cost_usd=_estimate_cost(prompt_tokens, completion_tokens),
        duration_ms=duration_ms,
        paper_id=paper_id,
    )
    db.add(call)
    db.commit()
    return call
