from app.services.cost_tracker import _estimate_cost
from app.config import Settings


def test_estimate_cost_gpt4o_mini():
    cost = _estimate_cost(1000, 500)
    assert cost > 0
    assert cost < 0.01


def test_estimate_cost_zero():
    cost = _estimate_cost(0, 0)
    assert cost == 0.0


def test_budget_check():
    s = Settings(daily_llm_budget_usd=5.0, require_approval_above_cost=0.10)
    assert s.daily_llm_budget_usd == 5.0
    assert s.require_approval_above_cost == 0.10
