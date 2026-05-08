from __future__ import annotations

from ai.stock_signal import Action, Confidence, analyze_ticker, analyze_with_bars
from ai.stock_signal.models import PriceBar
from ai.stock_signal.render import render_text


def _uptrend_bars(count: int = 260) -> list[PriceBar]:
    bars: list[PriceBar] = []
    price = 100.0
    for index in range(count):
        price *= 1.002
        bars.append(
            PriceBar(
                date=f"2026-01-{(index % 28) + 1:02d}",
                open=price * 0.995,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1_000_000 + index * 1_000,
            )
        )
    return bars


def _downtrend_bars(count: int = 260) -> list[PriceBar]:
    bars: list[PriceBar] = []
    price = 180.0
    for index in range(count):
        price *= 0.998
        bars.append(
            PriceBar(
                date=f"2026-02-{(index % 28) + 1:02d}",
                open=price * 1.005,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=1_000_000,
            )
        )
    return bars


def test_analyze_with_bars_returns_decision_brief_for_uptrend():
    brief = analyze_with_bars("AAPL", _uptrend_bars(), source="test")

    assert brief.ticker == "AAPL"
    assert 0 <= brief.score <= 100
    assert brief.action in {Action.ACTIONABLE_LONG, Action.CONDITIONAL_LONG}
    assert brief.confidence in {Confidence.MEDIUM, Confidence.HIGH}
    assert brief.entry_condition
    assert brief.invalidation
    assert brief.risk_reward is not None


def test_downtrend_is_not_actionable_long():
    brief = analyze_with_bars("XYZ", _downtrend_bars(), source="test")

    assert brief.action in {Action.HOLD_MONITOR, Action.REDUCE_RISK, Action.AVOID}
    assert brief.score < 60


def test_render_text_contains_required_sections():
    brief = analyze_with_bars("MSFT", _uptrend_bars(), source="test")
    text = render_text(brief)

    assert "Decision Brief" in text
    assert "Action:" in text
    assert "Entry condition" in text
    assert "Invalidation" in text
    assert "Risk / Reward" in text
    assert "This is decision-support analysis" in text


def test_offline_cli_engine_uses_synthetic_source():
    brief = analyze_ticker("TSLA", offline=True)

    assert brief.ticker == "TSLA"
    assert brief.data_quality.source == "synthetic"
    assert 0 <= brief.score <= 100
