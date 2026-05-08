from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    ACTIONABLE_LONG = "ACTIONABLE_LONG"
    CONDITIONAL_LONG = "CONDITIONAL_LONG"
    HOLD_MONITOR = "HOLD_MONITOR"
    REDUCE_RISK = "REDUCE_RISK"
    AVOID = "AVOID"


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Timeframe(str, Enum):
    SHORT_TERM = "SHORT_TERM"
    SWING = "SWING"
    POSITION = "POSITION"


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
    volume: int
    volatility_risk: int
    news_event: int
    market_regime: int

    @property
    def total(self) -> int:
        return max(
            0,
            min(
                100,
                self.trend
                + self.momentum
                + self.volume
                + self.volatility_risk
                + self.news_event
                + self.market_regime,
            ),
        )


@dataclass(frozen=True)
class DataQuality:
    price: str
    technicals: str
    news: str
    events: str
    source: str


@dataclass(frozen=True)
class StockDecisionBrief:
    ticker: str
    asset_type: str
    action: Action
    confidence: Confidence
    score: int
    timeframe: Timeframe
    reference_price: float
    entry_condition: str
    invalidation: str
    upside_reference_pct: float | None
    downside_reference_pct: float | None
    risk_reward: float | None
    reasons: list[str]
    risks: list[str]
    data_quality: DataQuality
    component_scores: ComponentScores
    generated_at: str
    disclaimer: str
