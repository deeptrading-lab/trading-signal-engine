from __future__ import annotations

from datetime import datetime, timezone

from .indicators import build_technical_snapshot
from .models import (
    Action,
    AllocationSizing,
    BitcoinAllocationBrief,
    ComponentScores,
    Confidence,
    DataQuality,
    MarketFlowSnapshot,
    NewsSnapshot,
    PriceBar,
    SizingBasis,
    TechnicalSnapshot,
    Timeframe,
)
from .llm import LLMProviderError, fetch_openai_bitcoin_news_snapshot
from .providers import BinanceMarketFlowProvider, BitcoinPriceProvider, PriceProviderError, SyntheticBitcoinPriceProvider


BITCOIN_SYMBOL = "BTC"
SUPPORTED_ALIASES = {"BTC", "BTC-USD", "BITCOIN", "비트코인", "비트"}
DISCLAIMER = (
    "This is Bitcoin allocation decision support, not financial advice or an automated order."
)


def normalize_bitcoin_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized not in SUPPORTED_ALIASES:
        raise ValueError("Bitcoin only MVP. Try `analyze BTC`.")
    return BITCOIN_SYMBOL


def analyze_bitcoin(
    symbol: str = BITCOIN_SYMBOL,
    *,
    timeframe: Timeframe = Timeframe.SWING,
    offline: bool = False,
    cash_amount: float | None = None,
    cash_currency: str | None = None,
    btc_holding_amount: float | None = None,
    data_provider: str = "none",
) -> BitcoinAllocationBrief:
    normalize_bitcoin_symbol(symbol)

    source = "synthetic"
    provider = SyntheticBitcoinPriceProvider() if offline else BitcoinPriceProvider()
    try:
        bars = provider.fetch_daily(BITCOIN_SYMBOL)
        source = "synthetic" if offline else "yahoo-chart:BTC-USD"
    except PriceProviderError:
        bars = SyntheticBitcoinPriceProvider().fetch_daily(BITCOIN_SYMBOL)
        source = "synthetic-fallback"

    news_snapshot = None
    market_flow_snapshot = None
    normalized_data_provider = data_provider.strip().lower()
    if not offline and normalized_data_provider == "openai":
        try:
            news_snapshot = fetch_openai_bitcoin_news_snapshot()
        except LLMProviderError:
            news_snapshot = None
        try:
            market_flow_snapshot = BinanceMarketFlowProvider().fetch_market_flow(BITCOIN_SYMBOL)
        except PriceProviderError:
            market_flow_snapshot = None

    return analyze_with_bars(
        bars,
        timeframe=timeframe,
        source=source,
        cash_amount=cash_amount,
        cash_currency=cash_currency,
        btc_holding_amount=btc_holding_amount,
        news_snapshot=news_snapshot,
        market_flow_snapshot=market_flow_snapshot,
    )


def analyze_with_bars(
    bars: list[PriceBar],
    *,
    timeframe: Timeframe = Timeframe.SWING,
    source: str = "provided",
    cash_amount: float | None = None,
    cash_currency: str | None = None,
    btc_holding_amount: float | None = None,
    news_snapshot: NewsSnapshot | None = None,
    market_flow_snapshot: MarketFlowSnapshot | None = None,
) -> BitcoinAllocationBrief:
    if len(bars) < 60:
        raise ValueError("at least 60 daily Bitcoin bars are required")

    technicals = build_technical_snapshot(bars)
    component_scores = _score_components(technicals, news_snapshot, market_flow_snapshot)
    score = component_scores.total
    downside_reference, upside_reference, risk_range_ratio = _risk_range(technicals)
    data_quality = DataQuality(
        price="fresh",
        technicals="complete" if technicals.sma_200 is not None else "partial",
        news="openai-web-search" if news_snapshot is not None else "unavailable",
        market_flows="binance-public" if market_flow_snapshot is not None else "unavailable",
        source=source,
    )
    action = _map_action(score, risk_range_ratio, data_quality, technicals)
    confidence = _map_confidence(score, data_quality, technicals, action)
    sizing = _build_sizing(
        action,
        confidence,
        data_quality,
        technicals,
        cash_amount=cash_amount,
        cash_currency=cash_currency,
        btc_holding_amount=btc_holding_amount,
    )
    reasons = _build_reasons(technicals, component_scores, news_snapshot, market_flow_snapshot)
    risks = _build_risks(technicals, data_quality, risk_range_ratio)

    return BitcoinAllocationBrief(
        symbol=BITCOIN_SYMBOL,
        asset_type="BITCOIN_SPOT",
        action=action,
        confidence=confidence,
        score=score,
        timeframe=timeframe,
        reference_price=technicals.last_price,
        allocation_condition=_allocation_condition(action, technicals),
        risk_off_condition=_risk_off_condition(technicals, downside_reference),
        upside_reference_pct=upside_reference,
        downside_reference_pct=downside_reference,
        risk_range_ratio=risk_range_ratio,
        sizing=sizing,
        reasons=reasons,
        risks=risks,
        data_quality=data_quality,
        news_snapshot=news_snapshot,
        market_flow_snapshot=market_flow_snapshot,
        component_scores=component_scores,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        disclaimer=DISCLAIMER,
    )


def _score_components(
    snapshot: TechnicalSnapshot,
    news_snapshot: NewsSnapshot | None = None,
    market_flow_snapshot: MarketFlowSnapshot | None = None,
) -> ComponentScores:
    last = snapshot.last_price

    trend = 0
    if snapshot.sma_20 and last > snapshot.sma_20:
        trend += 6
    if snapshot.sma_50 and last > snapshot.sma_50:
        trend += 7
    if snapshot.sma_200 and last > snapshot.sma_200:
        trend += 8
    if snapshot.sma_20 and snapshot.sma_50 and snapshot.sma_20 > snapshot.sma_50:
        trend += 3
    if snapshot.sma_50 and snapshot.sma_200 and snapshot.sma_50 > snapshot.sma_200:
        trend += 1

    momentum = 0
    if snapshot.return_20d is not None:
        momentum += _bucket(snapshot.return_20d, [(-5, 2), (0, 5), (8, 8), (15, 10)])
    if snapshot.return_60d is not None:
        momentum += _bucket(snapshot.return_60d, [(-10, 2), (0, 5), (12, 8), (25, 10)])

    participation = 6
    if snapshot.volume_ratio is not None:
        if snapshot.volume_ratio >= 1.5:
            participation = 15
        elif snapshot.volume_ratio >= 1.15:
            participation = 12
        elif snapshot.volume_ratio >= 0.8:
            participation = 9

    volatility_risk = 8
    if snapshot.volatility_20d is not None:
        if snapshot.volatility_20d <= 40:
            volatility_risk = 15
        elif snapshot.volatility_20d <= 60:
            volatility_risk = 11
        elif snapshot.volatility_20d <= 85:
            volatility_risk = 7
        else:
            volatility_risk = 3

    drawdown_penalty = _drawdown_from_high(snapshot)
    if drawdown_penalty is not None and drawdown_penalty <= -25:
        volatility_risk = min(volatility_risk, 7)

    news_flow = _score_news(news_snapshot)
    macro_regime = _score_market_flow(market_flow_snapshot)

    return ComponentScores(
        trend=min(25, trend),
        momentum=min(20, momentum),
        participation=min(15, participation),
        volatility_risk=min(15, volatility_risk),
        news_flow=news_flow,
        macro_regime=macro_regime,
    )


def _score_news(snapshot: NewsSnapshot | None) -> int:
    if snapshot is None:
        return 7
    if snapshot.sentiment == "bullish":
        return 10
    if snapshot.sentiment == "bearish":
        return 3
    return 7


def _score_market_flow(snapshot: MarketFlowSnapshot | None) -> int:
    if snapshot is None:
        return 6
    score = 6
    if snapshot.price_change_pct_24h > 2:
        score += 2
    elif snapshot.price_change_pct_24h < -2:
        score -= 2
    if snapshot.taker_buy_ratio_24h is not None:
        if snapshot.taker_buy_ratio_24h >= 0.54:
            score += 2
        elif snapshot.taker_buy_ratio_24h <= 0.46:
            score -= 2
    if snapshot.volume_vs_7d_avg is not None and snapshot.volume_vs_7d_avg >= 1.25:
        score += 1
    return max(0, min(10, score))


def _bucket(value: float, thresholds: list[tuple[float, int]]) -> int:
    score = 0
    for threshold, points in thresholds:
        if value >= threshold:
            score = points
    return score


def _drawdown_from_high(snapshot: TechnicalSnapshot) -> float | None:
    if not snapshot.high_52w:
        return None
    return (snapshot.last_price / snapshot.high_52w - 1.0) * 100.0


def _risk_range(snapshot: TechnicalSnapshot) -> tuple[float | None, float | None, float | None]:
    price = snapshot.last_price
    atr = snapshot.atr_14 or price * 0.04
    risk_candidates = [snapshot.sma_50, snapshot.sma_200, price - (2.5 * atr)]
    stop_candidate = min(value for value in risk_candidates if value is not None and value > 0)
    downside_pct = (stop_candidate / price - 1.0) * 100.0

    two_r_reference = price + abs(downside_pct / 100.0 * price) * 2.0
    upside_price = max(snapshot.high_52w or 0.0, two_r_reference)
    upside_pct = (upside_price / price - 1.0) * 100.0
    ratio = upside_pct / abs(downside_pct) if downside_pct < 0 else None
    return round(downside_pct, 2), round(upside_pct, 2), round(ratio, 2) if ratio else None


def _map_action(
    score: int,
    risk_range_ratio: float | None,
    data_quality: DataQuality,
    snapshot: TechnicalSnapshot,
) -> Action:
    if data_quality.price != "fresh":
        return Action.RISK_OFF
    if snapshot.volatility_20d is not None and snapshot.volatility_20d > 95:
        return Action.REDUCE_ALLOCATION
    if score < 35:
        return Action.RISK_OFF
    if score < 45:
        return Action.REDUCE_ALLOCATION
    if score < 60:
        return Action.MAINTAIN_ALLOCATION
    if risk_range_ratio is None or risk_range_ratio < 1.4:
        return Action.MAINTAIN_ALLOCATION
    if score >= 75 and snapshot.volatility_20d is not None and snapshot.volatility_20d <= 65:
        return Action.INCREASE_ALLOCATION
    return Action.CONDITIONAL_INCREASE


def _map_confidence(
    score: int,
    data_quality: DataQuality,
    snapshot: TechnicalSnapshot,
    action: Action,
) -> Confidence:
    if snapshot.volatility_20d is not None and snapshot.volatility_20d > 85:
        return Confidence.LOW
    if data_quality.news == "unavailable" or data_quality.market_flows == "unavailable":
        return Confidence.LOW if action in {Action.RISK_OFF, Action.REDUCE_ALLOCATION} else Confidence.MEDIUM
    if score >= 75:
        return Confidence.HIGH
    if score >= 55:
        return Confidence.MEDIUM
    return Confidence.LOW


def _allocation_condition(action: Action, snapshot: TechnicalSnapshot) -> str:
    if action == Action.INCREASE_ALLOCATION:
        return "BTC가 20일/50일 추세선 위를 유지하면 보유 현금 중 일부로 단계적 비중 확대 검토"
    if action == Action.CONDITIONAL_INCREASE:
        return "20일선 회복, 거래 참여 증가, 변동성 둔화가 함께 확인될 때만 소폭 비중 확대 검토"
    if action == Action.MAINTAIN_ALLOCATION:
        return "추가 매수보다 현재 비중 유지, 50일선과 변동성 방향을 우선 관찰"
    if action == Action.REDUCE_ALLOCATION:
        return "이미 보유 중이면 반등 구간에서 일부 현금화해 포트폴리오 변동성을 낮춤"
    return "신규 매수 보류, 현금 비중 유지"


def _build_sizing(
    action: Action,
    confidence: Confidence,
    data_quality: DataQuality,
    snapshot: TechnicalSnapshot,
    *,
    cash_amount: float | None,
    cash_currency: str | None,
    btc_holding_amount: float | None,
) -> AllocationSizing:
    normalized_cash = _positive_or_none(cash_amount)
    normalized_btc = _positive_or_none(btc_holding_amount)
    normalized_currency = _normalize_currency(cash_currency) if normalized_cash is not None else None

    if data_quality.price != "fresh":
        return AllocationSizing(
            sizing_basis=SizingBasis.NO_SIZE,
            available_seed_pct=None,
            btc_holdings_sell_pct=None,
            target_btc_allocation_pct=None,
            cash_amount=normalized_cash,
            cash_currency=normalized_currency,
            btc_holding_amount=normalized_btc,
            estimated_order_cash_amount=None,
            estimated_order_cash_currency=None,
            estimated_order_btc_amount=None,
            sizing_label_ko="가격 데이터가 오래되어 오늘은 구체적 매수/매도 비율을 내지 않습니다.",
            sizing_detail_ko="최신 가격을 다시 확인한 뒤 판단해야 합니다.",
        )

    if action in {Action.INCREASE_ALLOCATION, Action.CONDITIONAL_INCREASE}:
        pct = _buy_seed_pct(action, confidence, snapshot)
        estimated_cash = _round_money(normalized_cash * pct / 100.0) if normalized_cash is not None else None
        estimated_btc = (
            round(estimated_cash / snapshot.last_price, 8)
            if estimated_cash is not None and normalized_currency == "USD"
            else None
        )
        label = f"사용 가능 시드의 {pct:g}% 매수 검토"
        detail = _buy_detail(pct, estimated_cash, normalized_currency, estimated_btc)
        return AllocationSizing(
            sizing_basis=SizingBasis.AVAILABLE_SEED,
            available_seed_pct=pct,
            btc_holdings_sell_pct=None,
            target_btc_allocation_pct=None,
            cash_amount=normalized_cash,
            cash_currency=normalized_currency,
            btc_holding_amount=normalized_btc,
            estimated_order_cash_amount=estimated_cash,
            estimated_order_cash_currency=normalized_currency,
            estimated_order_btc_amount=estimated_btc,
            sizing_label_ko=label,
            sizing_detail_ko=detail,
        )

    if action in {Action.REDUCE_ALLOCATION, Action.RISK_OFF}:
        pct = 35.0 if action == Action.RISK_OFF else _sell_holding_pct(confidence, snapshot)
        estimated_btc = round(normalized_btc * pct / 100.0, 8) if normalized_btc is not None else None
        estimated_cash = round(estimated_btc * snapshot.last_price, 2) if estimated_btc is not None else None
        label = f"보유 BTC의 {pct:g}% 매도 검토"
        detail = _sell_detail(pct, estimated_btc, estimated_cash)
        return AllocationSizing(
            sizing_basis=SizingBasis.BTC_HOLDINGS,
            available_seed_pct=None,
            btc_holdings_sell_pct=pct,
            target_btc_allocation_pct=None,
            cash_amount=normalized_cash,
            cash_currency=normalized_currency,
            btc_holding_amount=normalized_btc,
            estimated_order_cash_amount=estimated_cash,
            estimated_order_cash_currency="USD" if estimated_cash is not None else None,
            estimated_order_btc_amount=estimated_btc,
            sizing_label_ko=label,
            sizing_detail_ko=detail,
        )

    return AllocationSizing(
        sizing_basis=SizingBasis.NO_SIZE,
        available_seed_pct=0.0,
        btc_holdings_sell_pct=None,
        target_btc_allocation_pct=None,
        cash_amount=normalized_cash,
        cash_currency=normalized_currency,
        btc_holding_amount=normalized_btc,
        estimated_order_cash_amount=0.0 if normalized_cash is not None else None,
        estimated_order_cash_currency=normalized_currency if normalized_cash is not None else None,
        estimated_order_btc_amount=0.0,
        sizing_label_ko="오늘은 추가 매수 없이 현재 비중 유지",
        sizing_detail_ko="방향성이 더 분명해질 때까지 현금과 보유 BTC 비중을 그대로 둡니다.",
    )


def _buy_seed_pct(action: Action, confidence: Confidence, snapshot: TechnicalSnapshot) -> float:
    if action == Action.INCREASE_ALLOCATION and confidence == Confidence.HIGH:
        if snapshot.volatility_20d is not None and snapshot.volatility_20d <= 45:
            return 10.0
    if action == Action.INCREASE_ALLOCATION:
        return 5.0
    if action == Action.CONDITIONAL_INCREASE and confidence in {Confidence.MEDIUM, Confidence.HIGH}:
        return 5.0
    return 0.0


def _sell_holding_pct(confidence: Confidence, snapshot: TechnicalSnapshot) -> float:
    if confidence == Confidence.LOW:
        return 15.0
    if snapshot.volatility_20d is not None and snapshot.volatility_20d > 75:
        return 15.0
    return 10.0


def _positive_or_none(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return value


def _normalize_currency(value: str | None) -> str:
    normalized = (value or "KRW").strip().upper()
    return normalized if normalized in {"KRW", "USD"} else "KRW"


def _round_money(value: float) -> float:
    return round(value, 2)


def _format_money(value: float, currency: str | None) -> str:
    if currency == "USD":
        return f"${value:,.2f}"
    return f"{value:,.0f}원"


def _buy_detail(
    pct: float,
    estimated_cash: float | None,
    currency: str | None,
    estimated_btc: float | None,
) -> str:
    if pct <= 0:
        return "조건이 부족해 오늘은 새 매수를 하지 않습니다."
    if estimated_cash is None:
        return f"현금 금액을 입력하면 {pct:g}%가 얼마인지 함께 계산합니다."
    if estimated_btc is not None:
        return f"조건이 맞으면 약 {_format_money(estimated_cash, currency)} 또는 {estimated_btc:g} BTC만 매수 검토합니다."
    return f"조건이 맞으면 약 {_format_money(estimated_cash, currency)}만 매수 검토합니다."


def _sell_detail(
    pct: float,
    estimated_btc: float | None,
    estimated_cash: float | None,
) -> str:
    if estimated_btc is None:
        return f"BTC 보유량을 입력하면 {pct:g}%가 몇 BTC인지 함께 계산합니다."
    if estimated_cash is not None:
        return f"보유 BTC 중 약 {estimated_btc:g} BTC 매도 검토. USD 기준 약 ${estimated_cash:,.2f}입니다."
    return f"보유 BTC 중 약 {estimated_btc:g} BTC 매도 검토."


def _risk_off_condition(snapshot: TechnicalSnapshot, downside_reference_pct: float | None) -> str:
    if snapshot.sma_200:
        return f"일봉 종가가 200일선({snapshot.sma_200:.2f}) 아래에서 유지되면 리스크오프 전환"
    if snapshot.sma_50:
        return f"일봉 종가가 50일선({snapshot.sma_50:.2f}) 아래로 재이탈하면 비중 축소"
    if downside_reference_pct is not None:
        return f"기준가 대비 {abs(downside_reference_pct):.1f}% 하락 시 비중 확대 시나리오 폐기"
    return "가격 데이터 부족으로 리스크오프 조건 산출 불가"


def _build_reasons(
    snapshot: TechnicalSnapshot,
    scores: ComponentScores,
    news_snapshot: NewsSnapshot | None = None,
    market_flow_snapshot: MarketFlowSnapshot | None = None,
) -> list[str]:
    reasons: list[str] = []
    if news_snapshot is not None:
        reasons.append(f"뉴스 흐름({news_snapshot.sentiment}): {news_snapshot.summary_ko}")
    if market_flow_snapshot is not None:
        reasons.append(f"거래소 매매 동향: {market_flow_snapshot.summary_ko}")
    if snapshot.sma_20 and snapshot.last_price > snapshot.sma_20:
        reasons.append(f"BTC가 20일 이동평균({snapshot.sma_20:.2f}) 위에 있어 단기 추세가 유지됨")
    if snapshot.sma_50 and snapshot.sma_200 and snapshot.sma_50 > snapshot.sma_200:
        reasons.append("50일선이 200일선 위에 있어 중기 추세 구조가 우호적")
    if snapshot.return_20d is not None:
        reasons.append(f"20일 BTC 수익률은 {snapshot.return_20d:.1f}%")
    if snapshot.return_60d is not None:
        reasons.append(f"60일 BTC 수익률은 {snapshot.return_60d:.1f}%")
    if snapshot.rsi_14 is not None:
        reasons.append(f"RSI 14는 {snapshot.rsi_14:.1f}로 과열/침체 구간을 점검해야 함")
    reasons.append(
        "점수 분해: "
        f"trend {scores.trend}/25, momentum {scores.momentum}/20, "
        f"participation {scores.participation}/15, risk {scores.volatility_risk}/15"
    )
    return reasons[:5]


def _build_risks(
    snapshot: TechnicalSnapshot,
    data_quality: DataQuality,
    risk_range_ratio: float | None,
) -> list[str]:
    risks: list[str] = []
    if data_quality.news == "unavailable":
        risks.append("뉴스 데이터가 아직 연결되지 않아 정책/규제/기관 수급 해석 신뢰도가 제한됨")
    if data_quality.market_flows == "unavailable":
        risks.append("온체인·거래소 수급 데이터가 없어 실제 매매 동향은 가격/거래량으로만 대체됨")
    if snapshot.volatility_20d is not None and snapshot.volatility_20d > 65:
        risks.append(f"20일 실현 변동성이 {snapshot.volatility_20d:.1f}%로 높아 비중 확대 후 손익 변동이 클 수 있음")
    if risk_range_ratio is not None and risk_range_ratio < 1.4:
        risks.append(f"상방/하방 참고 범위 비율이 {risk_range_ratio:.2f}로 공격적 확대 매력이 낮음")
    if not risks:
        risks.append("주요 가격 지표는 양호하나 24시간 시장 특성상 신호가 빠르게 낡을 수 있음")
    return risks[:4]
