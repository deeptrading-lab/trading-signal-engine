from __future__ import annotations

import pytest

from ai.bitcoin_signal import Action, Confidence, SizingBasis, analyze_bitcoin, analyze_with_bars
from ai.bitcoin_signal.config import load_openai_settings
from ai.bitcoin_signal.models import PriceBar
from ai.bitcoin_signal.render import render_text


def _uptrend_bars(count: int = 260) -> list[PriceBar]:
    bars: list[PriceBar] = []
    price = 60_000.0
    for index in range(count):
        price *= 1.002
        bars.append(
            PriceBar(
                date=f"2026-01-{(index % 28) + 1:02d}",
                open=price * 0.995,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=18_000_000_000 + index * 10_000_000,
            )
        )
    return bars


def _downtrend_bars(count: int = 260) -> list[PriceBar]:
    bars: list[PriceBar] = []
    price = 90_000.0
    for index in range(count):
        price *= 0.998
        bars.append(
            PriceBar(
                date=f"2026-02-{(index % 28) + 1:02d}",
                open=price * 1.005,
                high=price * 1.01,
                low=price * 0.99,
                close=price,
                volume=15_000_000_000,
            )
        )
    return bars


def test_analyze_with_bars_returns_bitcoin_allocation_brief_for_uptrend():
    brief = analyze_with_bars(_uptrend_bars(), source="test")

    assert brief.symbol == "BTC"
    assert brief.asset_type == "BITCOIN_SPOT"
    assert 0 <= brief.score <= 100
    assert brief.action in {Action.INCREASE_ALLOCATION, Action.CONDITIONAL_INCREASE}
    assert brief.confidence in {Confidence.MEDIUM, Confidence.HIGH}
    assert brief.allocation_condition
    assert brief.risk_off_condition
    assert brief.risk_range_ratio is not None
    assert brief.sizing.sizing_basis == SizingBasis.AVAILABLE_SEED


def test_downtrend_is_not_allocation_increase():
    brief = analyze_with_bars(_downtrend_bars(), source="test")

    assert brief.action in {Action.MAINTAIN_ALLOCATION, Action.REDUCE_ALLOCATION, Action.RISK_OFF}
    assert brief.score < 60


def test_render_text_contains_required_sections_and_no_stock_examples():
    brief = analyze_with_bars(_uptrend_bars(), source="test")
    text = render_text(brief)

    assert "Bitcoin Allocation Brief" in text
    assert "Action:" in text
    assert "Sizing" in text
    assert "Allocation condition" in text
    assert "Risk-off condition" in text
    assert "Risk range" in text
    assert "Bitcoin allocation decision support" in text
    assert "ETH" not in text
    assert "SOL" not in text


def test_offline_cli_engine_uses_synthetic_bitcoin_source():
    brief = analyze_bitcoin("BTC", offline=True)

    assert brief.symbol == "BTC"
    assert brief.data_quality.source == "synthetic"
    assert 0 <= brief.score <= 100


def test_usd_cash_input_returns_cash_and_btc_estimate_for_buy_sizing():
    brief = analyze_with_bars(
        _uptrend_bars(),
        source="test",
        cash_amount=1000,
        cash_currency="USD",
    )

    assert brief.sizing.sizing_basis == SizingBasis.AVAILABLE_SEED
    assert brief.sizing.available_seed_pct in {5.0, 10.0}
    assert brief.sizing.estimated_order_cash_amount in {50.0, 100.0}
    assert brief.sizing.estimated_order_btc_amount is not None
    assert "매수" in brief.sizing.sizing_label_ko


def test_krw_cash_input_hides_btc_estimate_until_conversion_provider_exists():
    brief = analyze_with_bars(
        _uptrend_bars(),
        source="test",
        cash_amount=1_000_000,
        cash_currency="KRW",
    )

    assert brief.sizing.estimated_order_cash_amount in {50_000.0, 100_000.0}
    assert brief.sizing.estimated_order_btc_amount is None
    assert "원" in brief.sizing.sizing_detail_ko


def test_btc_holding_input_returns_sell_amount_for_risk_off():
    brief = analyze_with_bars(
        _downtrend_bars(),
        source="test",
        btc_holding_amount=0.02,
    )

    assert brief.action in {Action.REDUCE_ALLOCATION, Action.RISK_OFF}
    assert brief.sizing.sizing_basis == SizingBasis.BTC_HOLDINGS
    assert brief.sizing.btc_holdings_sell_pct in {10.0, 15.0, 35.0}
    assert brief.sizing.estimated_order_btc_amount is not None


def test_openai_settings_defaults_do_not_require_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = load_openai_settings()

    assert settings.openai_api_key_configured is False
    assert settings.news_model == "gpt-5.4-nano"
    assert settings.brief_model == "gpt-5.4-mini"
    assert settings.monthly_billing_limit_usd == 20.0
    assert settings.daily_cost_limit_usd == 0.5


@pytest.mark.parametrize("symbol", ["ETH", "SOL", "XRP"])
def test_non_bitcoin_symbols_are_rejected(symbol: str):
    with pytest.raises(ValueError, match="Bitcoin only"):
        analyze_bitcoin(symbol, offline=True)
