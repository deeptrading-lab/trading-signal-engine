from __future__ import annotations

from datetime import datetime, timezone

from .indicators import build_technical_snapshot
from .models import (
    Action,
    ComponentScores,
    Confidence,
    DataQuality,
    PriceBar,
    StockDecisionBrief,
    TechnicalSnapshot,
    Timeframe,
)
from .providers import PriceProviderError, YahooChartPriceProvider, SyntheticPriceProvider


DISCLAIMER = "This is decision-support analysis, not an automated order."


def analyze_ticker(
    ticker: str,
    *,
    timeframe: Timeframe = Timeframe.SWING,
    offline: bool = False,
) -> StockDecisionBrief:
    normalized = ticker.strip().upper()
    if not normalized:
        raise ValueError("ticker is required")

    source = "synthetic"
    provider = SyntheticPriceProvider() if offline else YahooChartPriceProvider()
    try:
        bars = provider.fetch_daily(normalized)
        source = "synthetic" if offline else "yahoo-chart"
    except PriceProviderError:
        bars = SyntheticPriceProvider().fetch_daily(normalized)
        source = "synthetic-fallback"

    return analyze_with_bars(normalized, bars, timeframe=timeframe, source=source)


def analyze_with_bars(
    ticker: str,
    bars: list[PriceBar],
    *,
    timeframe: Timeframe = Timeframe.SWING,
    source: str = "provided",
) -> StockDecisionBrief:
    if len(bars) < 60:
        raise ValueError("at least 60 daily bars are required")

    technicals = build_technical_snapshot(bars)
    component_scores = _score_components(technicals)
    score = component_scores.total
    downside_reference, upside_reference, risk_reward = _risk_reward(technicals)
    data_quality = DataQuality(
        price="fresh",
        technicals="complete" if technicals.sma_200 is not None else "partial",
        news="none",
        events="unavailable",
        source=source,
    )
    action = _map_action(score, risk_reward, data_quality, technicals)
    confidence = _map_confidence(score, data_quality, technicals, action)
    reasons = _build_reasons(technicals, component_scores)
    risks = _build_risks(technicals, data_quality, risk_reward)

    return StockDecisionBrief(
        ticker=ticker.upper(),
        asset_type="US_EQUITY_OR_ETF",
        action=action,
        confidence=confidence,
        score=score,
        timeframe=timeframe,
        reference_price=technicals.last_price,
        entry_condition=_entry_condition(action, technicals),
        invalidation=_invalidation(technicals, downside_reference),
        upside_reference_pct=upside_reference,
        downside_reference_pct=downside_reference,
        risk_reward=risk_reward,
        reasons=reasons,
        risks=risks,
        data_quality=data_quality,
        component_scores=component_scores,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        disclaimer=DISCLAIMER,
    )


def _score_components(snapshot: TechnicalSnapshot) -> ComponentScores:
    last = snapshot.last_price

    trend = 0
    if snapshot.sma_20 and last > snapshot.sma_20:
        trend += 6
    if snapshot.sma_50 and last > snapshot.sma_50:
        trend += 6
    if snapshot.sma_200 and last > snapshot.sma_200:
        trend += 6
    if snapshot.sma_20 and snapshot.sma_50 and snapshot.sma_20 > snapshot.sma_50:
        trend += 4
    if snapshot.sma_50 and snapshot.sma_200 and snapshot.sma_50 > snapshot.sma_200:
        trend += 3

    momentum = 0
    if snapshot.return_20d is not None:
        momentum += _bucket(snapshot.return_20d, [(0, 4), (4, 7), (8, 10)])
    if snapshot.return_60d is not None:
        momentum += _bucket(snapshot.return_60d, [(0, 3), (8, 6), (15, 8)])
    if snapshot.rsi_14 is not None:
        if 45 <= snapshot.rsi_14 <= 68:
            momentum += 2
        elif 35 <= snapshot.rsi_14 < 45 or 68 < snapshot.rsi_14 <= 75:
            momentum += 1

    volume = 7
    if snapshot.volume_ratio is not None:
        if snapshot.volume_ratio >= 1.5:
            volume = 15
        elif snapshot.volume_ratio >= 1.15:
            volume = 12
        elif snapshot.volume_ratio >= 0.8:
            volume = 9

    volatility_risk = 8
    if snapshot.volatility_20d is not None:
        if snapshot.volatility_20d <= 25:
            volatility_risk = 15
        elif snapshot.volatility_20d <= 40:
            volatility_risk = 11
        elif snapshot.volatility_20d <= 60:
            volatility_risk = 7
        else:
            volatility_risk = 3

    # MVP has no paid news/event provider. Neutral score plus explicit data-quality flag.
    news_event = 7
    market_regime = 6

    return ComponentScores(
        trend=min(25, trend),
        momentum=min(20, momentum),
        volume=min(15, volume),
        volatility_risk=min(15, volatility_risk),
        news_event=news_event,
        market_regime=market_regime,
    )


def _bucket(value: float, thresholds: list[tuple[float, int]]) -> int:
    score = 0
    for threshold, points in thresholds:
        if value >= threshold:
            score = points
    return score


def _risk_reward(snapshot: TechnicalSnapshot) -> tuple[float | None, float | None, float | None]:
    price = snapshot.last_price
    atr = snapshot.atr_14 or price * 0.03
    stop_candidate = min(
        value
        for value in [snapshot.sma_50, price - (2.0 * atr)]
        if value is not None and value > 0
    )
    downside_pct = (stop_candidate / price - 1.0) * 100.0

    two_r_target = price + abs(downside_pct / 100.0 * price) * 2.0
    upside_price = max(snapshot.high_52w or 0.0, two_r_target)
    upside_pct = (upside_price / price - 1.0) * 100.0
    risk_reward = upside_pct / abs(downside_pct) if downside_pct < 0 else None
    return round(downside_pct, 2), round(upside_pct, 2), round(risk_reward, 2) if risk_reward else None


def _map_action(
    score: int,
    risk_reward: float | None,
    data_quality: DataQuality,
    snapshot: TechnicalSnapshot,
) -> Action:
    if data_quality.price != "fresh":
        return Action.AVOID
    if score < 35:
        return Action.AVOID
    if score < 45:
        return Action.REDUCE_RISK
    if score < 60:
        return Action.HOLD_MONITOR
    if risk_reward is None or risk_reward < 1.5:
        return Action.HOLD_MONITOR
    if score >= 75 and snapshot.volatility_20d is not None and snapshot.volatility_20d <= 45:
        return Action.ACTIONABLE_LONG
    return Action.CONDITIONAL_LONG


def _map_confidence(
    score: int,
    data_quality: DataQuality,
    snapshot: TechnicalSnapshot,
    action: Action,
) -> Confidence:
    if data_quality.news in {"unavailable", "none"} or data_quality.events == "unavailable":
        return Confidence.LOW if action in {Action.AVOID, Action.REDUCE_RISK} else Confidence.MEDIUM
    if snapshot.volatility_20d is not None and snapshot.volatility_20d > 60:
        return Confidence.LOW
    if score >= 75:
        return Confidence.HIGH
    if score >= 55:
        return Confidence.MEDIUM
    return Confidence.LOW


def _entry_condition(action: Action, snapshot: TechnicalSnapshot) -> str:
    if action == Action.ACTIONABLE_LONG:
        return "현재가가 20일선 위를 유지하고 거래량이 평균 이상이면 분할 진입 검토"
    if action == Action.CONDITIONAL_LONG:
        return "20일선 위 회복 또는 평균 대비 1.15배 이상 거래량 확인 후 진입 검토"
    if action == Action.HOLD_MONITOR:
        return "방향성 확인 전까지 관망, 20일선과 50일선 재돌파 여부 관찰"
    if action == Action.REDUCE_RISK:
        return "보유 중이면 반등 시 비중 축소 검토"
    return "신규 진입 회피"


def _invalidation(snapshot: TechnicalSnapshot, downside_reference_pct: float | None) -> str:
    if snapshot.sma_50:
        return f"종가 기준 50일선({snapshot.sma_50:.2f}) 이탈 시 시나리오 폐기"
    if downside_reference_pct is not None:
        return f"기준가 대비 {abs(downside_reference_pct):.1f}% 하락 시 시나리오 폐기"
    return "가격 데이터 부족으로 무효 조건 산출 불가"


def _build_reasons(snapshot: TechnicalSnapshot, scores: ComponentScores) -> list[str]:
    reasons: list[str] = []
    if snapshot.sma_20 and snapshot.last_price > snapshot.sma_20:
        reasons.append(f"현재가가 20일 이동평균({snapshot.sma_20:.2f}) 위에 있어 단기 추세가 유지됨")
    if snapshot.sma_50 and snapshot.sma_200 and snapshot.sma_50 > snapshot.sma_200:
        reasons.append("50일선이 200일선 위에 있어 중기 추세 구조가 우호적")
    if snapshot.return_20d is not None:
        reasons.append(f"20거래일 수익률은 {snapshot.return_20d:.1f}%")
    if snapshot.rsi_14 is not None:
        reasons.append(f"RSI 14는 {snapshot.rsi_14:.1f}로 과열/침체 여부를 확인할 수 있음")
    reasons.append(f"점수 분해: trend {scores.trend}/25, momentum {scores.momentum}/20, risk {scores.volatility_risk}/15")
    return reasons[:5]


def _build_risks(
    snapshot: TechnicalSnapshot,
    data_quality: DataQuality,
    risk_reward: float | None,
) -> list[str]:
    risks: list[str] = []
    if data_quality.news == "none":
        risks.append("뉴스 데이터는 MVP에서 아직 연결되지 않아 이벤트 해석 신뢰도가 제한됨")
    if data_quality.events == "unavailable":
        risks.append("실적/공시 일정 데이터가 없어 이벤트 리스크를 보수적으로 봐야 함")
    if snapshot.volatility_20d is not None and snapshot.volatility_20d > 45:
        risks.append(f"20일 변동성이 {snapshot.volatility_20d:.1f}%로 높아 진입 후 흔들림이 클 수 있음")
    if risk_reward is not None and risk_reward < 1.5:
        risks.append(f"리스크/보상 비율이 {risk_reward:.2f}로 신규 진입 매력이 낮음")
    if not risks:
        risks.append("주요 가격 지표는 양호하나 장중 급변 시 신호가 빠르게 낡을 수 있음")
    return risks[:4]
