"""Token accounting, cost calculation, and budget enforcement."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from db import get_setting, get_usage_summary, record_usage


class BudgetExceededError(Exception):
    """Raised when monthly token budget has reached 100% and user has not overridden."""
    pass


def calculate_cost(
    model: str, input_tokens: int, output_tokens: int, pricing_table: Optional[Dict[str, Any]] = None
) -> float:
    """Calculate estimated cost in USD based on model pricing per million tokens."""
    prices = pricing_table or get_setting("pricing", {}) or {}

    model_rates = prices.get(model)
    if not model_rates:
        # Check prefix match (e.g. 'claude-3-5-haiku-20241022' matches 'claude-3-5-haiku')
        for k, v in prices.items():
            if k in model:
                model_rates = v
                break

    if not model_rates:
        model_rates = prices.get("default", {"input": 2.0, "output": 8.0})

    in_rate = model_rates.get("input", 2.0)
    out_rate = model_rates.get("output", 8.0)

    cost = (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate
    return round(cost, 6)


def check_budget_status() -> Tuple[bool, Optional[str], float, float]:
    """Check monthly budget status.

    Returns:
        (is_allowed: bool, warning_or_error: Optional[str], current_cost: float, budget_limit: float)
    """
    budget_cfg = get_setting("budget", {}) or {}
    monthly_budget = float(budget_cfg.get("monthly_budget", 0.0))
    hard_stop = bool(budget_cfg.get("hard_stop", True))
    user_overridden = bool(budget_cfg.get("user_overridden", False))

    if monthly_budget <= 0.0:
        # No budget limit configured
        return True, None, 0.0, 0.0

    summary = get_usage_summary()
    current_cost = summary.get("calendar_month_cost", 0.0)

    pct = (current_cost / monthly_budget) * 100.0 if monthly_budget > 0 else 0.0

    if pct >= 100.0:
        if user_overridden:
            return True, f"Warning: Monthly budget limit reached (100% of ${monthly_budget:.2f}), override active.", current_cost, monthly_budget
        if hard_stop:
            return False, f"Monthly budget limit reached: ${current_cost:.2f} / ${monthly_budget:.2f} (100%). Requests paused.", current_cost, monthly_budget
        else:
            return True, f"Warning: Monthly budget exceeded (${current_cost:.2f} / ${monthly_budget:.2f}).", current_cost, monthly_budget

    if pct >= 80.0:
        return True, f"Notice: Monthly budget at {pct:.1f}% (${current_cost:.2f} / ${monthly_budget:.2f}).", current_cost, monthly_budget

    return True, None, current_cost, monthly_budget


def track_and_record_usage(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    conversation_id: Optional[str] = None,
) -> float:
    """Calculate cost and record token usage in database."""
    cost = calculate_cost(model, input_tokens, output_tokens)
    record_usage(
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        conversation_id=conversation_id,
    )
    return cost
