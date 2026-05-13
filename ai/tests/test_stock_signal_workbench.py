from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ai.stock_signal.models import AnalysisInput, TargetFeasibility, WorkbenchAction
from ai.stock_signal import server as server_module
from ai.stock_signal.server import _reset_rate_limit_state, _to_jsonable
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


def test_workbench_api_requires_configured_authentication(monkeypatch):
    _reset_rate_limit_state()
    monkeypatch.delenv("WORKBENCH_API_KEYS", raising=False)
    monkeypatch.delenv("ALLOW_UNAUTHENTICATED_WORKBENCH", raising=False)

    response = TestClient(server_module.app).post(
        "/api/workbench/analyze",
        json={
            "ticker": "AAPL",
            "capital_amount": 10_000,
            "target_return_pct": 8,
            "target_period_days": 90,
            "offline": True,
        },
    )

    assert response.status_code == 503
    assert "authentication is not configured" in response.json()["detail"]


def test_workbench_api_accepts_valid_api_key(monkeypatch):
    _reset_rate_limit_state()
    monkeypatch.setenv("WORKBENCH_API_KEYS", "test-key")

    response = TestClient(server_module.app).post(
        "/api/workbench/analyze",
        headers={"X-API-Key": "test-key"},
        json={
            "ticker": "AAPL",
            "capital_amount": 10_000,
            "target_return_pct": 8,
            "target_period_days": 90,
            "offline": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["analysis"]["whitelist_entry"]["ticker"] == "AAPL"


def test_workbench_api_rate_limits_authenticated_requests(monkeypatch):
    _reset_rate_limit_state()
    monkeypatch.setenv("WORKBENCH_API_KEYS", "test-key")
    monkeypatch.setenv("WORKBENCH_RATE_LIMIT_REQUESTS", "1")
    monkeypatch.setenv("WORKBENCH_RATE_LIMIT_WINDOW_SECONDS", "60")
    client = TestClient(server_module.app)
    payload = {
        "ticker": "AAPL",
        "capital_amount": 10_000,
        "target_return_pct": 8,
        "target_period_days": 90,
        "offline": True,
    }

    assert client.post("/api/workbench/analyze", headers={"X-API-Key": "test-key"}, json=payload).status_code == 200
    assert client.post("/api/workbench/analyze", headers={"X-API-Key": "test-key"}, json=payload).status_code == 429


def test_workbench_api_hides_unexpected_exception_detail(monkeypatch):
    _reset_rate_limit_state()
    monkeypatch.setenv("WORKBENCH_API_KEYS", "test-key")

    def raise_unexpected(*args, **kwargs):
        raise RuntimeError("provider secret stack trace")

    monkeypatch.setattr(server_module, "analyze_workbench", raise_unexpected)

    response = TestClient(server_module.app).post(
        "/api/workbench/analyze",
        headers={"Authorization": "Bearer test-key"},
        json={
            "ticker": "AAPL",
            "capital_amount": 10_000,
            "target_return_pct": 8,
            "target_period_days": 90,
            "offline": True,
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Analysis failed unexpectedly"
