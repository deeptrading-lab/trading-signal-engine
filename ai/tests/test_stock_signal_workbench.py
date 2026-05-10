from __future__ import annotations

import pytest

from ai.stock_signal.models import AnalysisInput, TargetFeasibility, WorkbenchAction
from ai.stock_signal.server import _to_jsonable
from ai.stock_signal.whitelist import WhitelistError, get_whitelist_entry
from ai.stock_signal.workbench import analyze_workbench


def test_whitelist_allows_apple_and_bitcoin_aliases():
    assert get_whitelist_entry("AAPL").ticker == "AAPL"
    assert get_whitelist_entry("apple").ticker == "AAPL"
    assert get_whitelist_entry("BTC").ticker == "BTC-USD"
    assert get_whitelist_entry("bitcoin").ticker == "BTC-USD"


def test_whitelist_rejects_unknown_ticker():
    with pytest.raises(WhitelistError):
        get_whitelist_entry("MSFT")


def test_workbench_generates_apple_domain_analysis_offline():
    analysis = analyze_workbench(
        AnalysisInput(
            ticker="AAPL",
            capital_amount=10_000,
            target_return_pct=8,
            target_period_days=90,
        ),
        offline=True,
    )

    assert analysis.whitelist_entry.ticker == "AAPL"
    assert len(analysis.horizons) == 6
    assert analysis.risk_plan.suggested_buy_amount > 0
    assert analysis.risk_plan.stop_loss_price_for_day < analysis.risk_plan.entry_price
    assert analysis.risk_plan.take_profit_price_for_day > analysis.risk_plan.entry_price
    assert analysis.action in set(WorkbenchAction)


def test_workbench_marks_stretched_bitcoin_goal_as_not_actionable_when_extreme():
    analysis = analyze_workbench(
        AnalysisInput(
            ticker="BTC",
            capital_amount=5_000,
            target_return_pct=50,
            target_period_days=30,
        ),
        offline=True,
    )

    assert analysis.whitelist_entry.ticker == "BTC-USD"
    assert analysis.feasibility == TargetFeasibility.UNREALISTIC
    assert analysis.action != WorkbenchAction.ACTIONABLE_BUY


def test_workbench_analysis_is_jsonable_for_api_response():
    analysis = analyze_workbench(
        AnalysisInput(
            ticker="AAPL",
            capital_amount=10_000,
            target_return_pct=8,
            target_period_days=90,
        ),
        offline=True,
    )

    payload = _to_jsonable(analysis)

    assert payload["whitelist_entry"]["ticker"] == "AAPL"
    assert payload["risk_plan"]["suggested_buy_amount"] > 0
    assert isinstance(payload["horizons"], list)
