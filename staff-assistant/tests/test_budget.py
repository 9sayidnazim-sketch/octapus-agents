import sys
from pathlib import Path
import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db import init_db, record_usage, set_setting
from usage_tracker import check_budget_status, calculate_cost


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Isolate database for budget tests."""
    test_db = tmp_path / "test_budget.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{test_db}")
    init_db(test_db)
    yield


def test_budget_80_percent_warning():
    """Verify warning returned when monthly budget hits 80%."""
    set_setting("budget", {"monthly_budget": 10.0, "hard_stop": True, "user_overridden": False})

    # Record $8.50 usage (85%)
    record_usage(provider="openai", model="gpt-4o", input_tokens=1000, output_tokens=1000, cost=8.50)

    allowed, notice, current_cost, limit = check_budget_status()
    assert allowed is True
    assert notice is not None
    assert "85.0%" in notice
    assert current_cost == 8.50
    assert limit == 10.0


def test_budget_100_percent_hard_stop():
    """Verify requests blocked when monthly budget hits 100% with hard stop."""
    set_setting("budget", {"monthly_budget": 10.0, "hard_stop": True, "user_overridden": False})

    # Record $10.50 usage (105%)
    record_usage(provider="openai", model="gpt-4o", input_tokens=1000, output_tokens=1000, cost=10.50)

    allowed, error, current_cost, limit = check_budget_status()
    assert allowed is False
    assert "limit reached" in error.lower()


def test_budget_100_percent_user_override():
    """Verify requests allowed when user has explicitly overridden the budget."""
    set_setting("budget", {"monthly_budget": 10.0, "hard_stop": True, "user_overridden": True})

    record_usage(provider="openai", model="gpt-4o", input_tokens=1000, output_tokens=1000, cost=10.50)

    allowed, notice, _, _ = check_budget_status()
    assert allowed is True
    assert "override active" in notice.lower()
