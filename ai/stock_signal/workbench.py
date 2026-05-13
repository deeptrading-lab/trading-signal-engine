from __future__ import annotations

from .engine import analyze_with_bars
from .feasibility import evaluate_target_feasibility
from .horizons import build_horizon_summaries
from .indicators import build_technical_snapshot
from .models import (
    Action,
    AnalysisInput,
    PositionState,
    PriceBar,
    RiskPlan,
    RiskTier,
    TargetFeasibility,
    TechnicalSnapshot,
    Timeframe,
    Trade,
    WorkbenchAction,
    WorkbenchAnalysis,
)
from .positions import calculate_position_state
from .providers import PriceProviderError, SyntheticPriceProvider, YahooChartPriceProvider
from .whitelist import get_whitelist_entry


def analyze_workbench(
    analysis_input: AnalysisInput,
    *,
    trades: list[Trade] | None = None,
    offline: bool = False,
) -> WorkbenchAnalysis:
    if analysis_input.capital_amount <= 0:
        raise ValueError("capital_amount must be positive")
    if analysis_input.target_return_pct < 0:
        raise ValueError("target_return_pct cannot be negative")
    if analysis_input.target_period_days <= 0:
        raise ValueError("target_period_days must be positive")

    whitelist_entry = get_whitelist_entry(analysis_input.ticker)
    bars, source, warnings = _fetch_bars(whitelist_entry.ticker, offline=offline)
    technicals = build_technical_snapshot(bars)
    brief = analyze_with_bars(whitelist_entry.ticker, bars, timeframe=Timeframe.SWING, source=source)
    feasibility, annualized = evaluate_target_feasibility(analysis_input, technicals, whitelist_entry)
    risk_plan = build_risk_plan(analysis_input, technicals, feasibility, whitelist_entry.risk_tier)
    position = (
        calculate_position_state(trades, market_price=technicals.last_price)
        if trades is not None
        else None
    )
    return WorkbenchAnalysis(
        input=analysis_input,
        whitelist_entry=whitelist_entry,
        brief=brief,
        feasibility=feasibility,
        annualized_target_return_pct=annualized,
        horizons=build_horizon_summaries(bars),
        risk_plan=risk_plan,
        position=position,
        action=_map_workbench_action(brief.action, feasibility, position),
        ai_summary=None,
        warnings=warnings,
    )


def build_risk_plan(
    analysis_input: AnalysisInput,
    technicals: TechnicalSnapshot,
    feasibility: TargetFeasibility,
    risk_tier: RiskTier,
) -> RiskPlan:
    price = technicals.last_price
    atr = technicals.atr_14 or price * 0.03
    max_loss_pct = max(0.25, min(analysis_input.max_loss_pct, 5.0))
    risk_budget = analysis_input.capital_amount * (max_loss_pct / 100.0)

    stop_distance = max(atr * 1.5, price * 0.02)
    if risk_tier == RiskTier.SPECULATIVE:
        risk_budget *= 0.5
        stop_distance = max(stop_distance, price * 0.04)
    elif risk_tier == RiskTier.HIGH:
        risk_budget *= 0.75

    if feasibility == TargetFeasibility.UNREALISTIC:
        risk_budget *= 0.5

    quantity = risk_budget / stop_distance if stop_distance > 0 else 0.0
    buy_amount = min(analysis_input.capital_amount, quantity * price)
    quantity = buy_amount / price if price > 0 else 0.0
    stop_loss = max(0.01, price - stop_distance)
    take_profit = price + stop_distance * 2.0
    expected_loss = max(0.0, (price - stop_loss) * quantity)
    expected_gain = max(0.0, (take_profit - price) * quantity)
    risk_reward = expected_gain / expected_loss if expected_loss > 0 else None

    return RiskPlan(
        suggested_buy_amount=round(buy_amount, 2),
        suggested_share_qty=round(quantity, 8),
        entry_price=round(price, 4),
        take_profit_price_for_day=round(take_profit, 4),
        stop_loss_price_for_day=round(stop_loss, 4),
        invalidation_condition=f"기준가 {price:.2f}에서 손절 기준 {stop_loss:.2f} 이탈 시 시나리오 재검토",
        expected_loss_if_stopped=round(expected_loss, 2),
        expected_gain_if_take_profit=round(expected_gain, 2),
        risk_reward_ratio=round(risk_reward, 2) if risk_reward is not None else None,
    )


def _fetch_bars(ticker: str, *, offline: bool) -> tuple[list[PriceBar], str, list[str]]:
    if offline:
        return SyntheticPriceProvider().fetch_daily(ticker), "synthetic", []
    try:
        return YahooChartPriceProvider().fetch_daily(ticker), "yahoo-chart", []
    except PriceProviderError as error:
        return (
            SyntheticPriceProvider().fetch_daily(ticker),
            "synthetic-fallback",
            [f"가격 데이터 제공자 호출 실패로 샘플 데이터를 사용했습니다: {error}"],
        )


def _map_workbench_action(
    action: Action,
    feasibility: TargetFeasibility,
    position: PositionState | None,
) -> WorkbenchAction:
    if feasibility == TargetFeasibility.UNREALISTIC and action in {
        Action.ACTIONABLE_LONG,
        Action.CONDITIONAL_LONG,
    }:
        return WorkbenchAction.HOLD

    has_position = position is not None and position.quantity > 0
    if action == Action.ACTIONABLE_LONG:
        return WorkbenchAction.CONDITIONAL_BUY if has_position else WorkbenchAction.ACTIONABLE_BUY
    if action == Action.CONDITIONAL_LONG:
        return WorkbenchAction.CONDITIONAL_BUY
    if action == Action.HOLD_MONITOR:
        return WorkbenchAction.HOLD
    if action == Action.REDUCE_RISK:
        return WorkbenchAction.PARTIAL_SELL if has_position else WorkbenchAction.AVOID
    return WorkbenchAction.SELL if has_position else WorkbenchAction.AVOID
