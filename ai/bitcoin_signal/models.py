from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    INCREASE_ALLOCATION = "INCREASE_ALLOCATION"
    CONDITIONAL_INCREASE = "CONDITIONAL_INCREASE"
    MAINTAIN_ALLOCATION = "MAINTAIN_ALLOCATION"
    REDUCE_ALLOCATION = "REDUCE_ALLOCATION"
    RISK_OFF = "RISK_OFF"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Timeframe(str, Enum):
    SHORT_TERM = "SHORT_TERM"
    SWING = "SWING"
    POSITION = "POSITION"


class SizingBasis(str, Enum):
    AVAILABLE_SEED = "AVAILABLE_SEED"
    BTC_HOLDINGS = "BTC_HOLDINGS"
    PORTFOLIO_TARGET = "PORTFOLIO_TARGET"
    NO_SIZE = "NO_SIZE"


@dataclass(frozen=True)
class PriceBar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class TechnicalSnapshot:
    last_price: float
    sma_20: float | None
    sma_50: float | None
    sma_200: float | None
    rsi_14: float | None
    return_20d: float | None
    return_60d: float | None
    volatility_20d: float | None
    volume_ratio: float | None
    high_52w: float | None
    low_52w: float | None
    atr_14: float | None


@dataclass(frozen=True)
class ComponentScores:
    trend: int
    momentum: int
    participation: int
    volatility_risk: int
    news_flow: int
    macro_regime: int

    @property
    def total(self) -> int:
        return max(
            0,
            min(
                100,
                self.trend
                + self.momentum
                + self.participation
                + self.volatility_risk
                + self.news_flow
                + self.macro_regime,
            ),
        )


@dataclass(frozen=True)
class DataQuality:
    price: str
    technicals: str
    news: str
    market_flows: str
    source: str


@dataclass(frozen=True)
class NewsSnapshot:
    summary_ko: str
    sentiment: str
    source_count: int
    sources: list[str]
    input_tokens: int | None
    output_tokens: int | None
    estimated_cost_usd: float | None
    error: str | None = None


@dataclass(frozen=True)
class MarketFlowSnapshot:
    source: str
    symbol: str
    price_change_pct_24h: float
    quote_volume_24h: float
    taker_buy_quote_volume_24h: float | None
    taker_buy_ratio_24h: float | None
    volume_vs_7d_avg: float | None
    summary_ko: str
    error: str | None = None


@dataclass(frozen=True)
class AllocationSizing:
    sizing_basis: SizingBasis
    available_seed_pct: float | None
    btc_holdings_sell_pct: float | None
    target_btc_allocation_pct: float | None
    cash_amount: float | None
    cash_currency: str | None
    btc_holding_amount: float | None
    estimated_order_cash_amount: float | None
    estimated_order_cash_currency: str | None
    estimated_order_btc_amount: float | None
    sizing_label_ko: str
    sizing_detail_ko: str


@dataclass(frozen=True)
class BitcoinAllocationBrief:
    symbol: str
    asset_type: str
    action: Action
    confidence: Confidence
    score: int
    timeframe: Timeframe
    reference_price: float
    allocation_condition: str
    risk_off_condition: str
    upside_reference_pct: float | None
    downside_reference_pct: float | None
    risk_range_ratio: float | None
    sizing: AllocationSizing
    reasons: list[str]
    risks: list[str]
    data_quality: DataQuality
    news_snapshot: NewsSnapshot | None
    market_flow_snapshot: MarketFlowSnapshot | None
    component_scores: ComponentScores
    generated_at: str
    disclaimer: str
