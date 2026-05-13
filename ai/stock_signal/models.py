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


class AssetType(str, Enum):
    US_EQUITY = "US_EQUITY"
    CRYPTO = "CRYPTO"


class RiskTier(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    SPECULATIVE = "SPECULATIVE"


class TargetFeasibility(str, Enum):
    REALISTIC = "REALISTIC"
    STRETCHED = "STRETCHED"
    UNREALISTIC = "UNREALISTIC"


class WorkbenchAction(str, Enum):
    ACTIONABLE_BUY = "ACTIONABLE_BUY"
    CONDITIONAL_BUY = "CONDITIONAL_BUY"
    HOLD = "HOLD"
    PARTIAL_SELL = "PARTIAL_SELL"
    SELL = "SELL"
    AVOID = "AVOID"


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


@dataclass(frozen=True)
class WhitelistEntry:
    ticker: str
    name: str
    asset_type: AssetType
    exchange: str
    currency: str
    sector: str
    enabled: bool
    risk_tier: RiskTier
    aliases: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class AnalysisInput:
    ticker: str
    capital_amount: float
    target_return_pct: float
    target_period_days: int
    risk_preference: str = "BALANCED"
    max_loss_pct: float = 2.0


@dataclass(frozen=True)
class HorizonSummary:
    label: str
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    high: float
    low: float
    return_pct: float
    max_drawdown_pct: float
    volume_change_pct: float | None
    direction: str


@dataclass(frozen=True)
class RiskPlan:
    suggested_buy_amount: float
    suggested_share_qty: float
    entry_price: float
    take_profit_price_for_day: float
    stop_loss_price_for_day: float
    invalidation_condition: str
    expected_loss_if_stopped: float
    expected_gain_if_take_profit: float
    risk_reward_ratio: float | None


@dataclass(frozen=True)
class Trade:
    side: str
    quantity: float
    price: float
    fee: float = 0.0


@dataclass(frozen=True)
class PositionState:
    quantity: float
    average_price: float | None
    realized_pnl: float
    market_value: float
    unrealized_pnl: float


@dataclass(frozen=True)
class WorkbenchAnalysis:
    input: AnalysisInput
    whitelist_entry: WhitelistEntry
    brief: StockDecisionBrief
    feasibility: TargetFeasibility
    annualized_target_return_pct: float
    horizons: list[HorizonSummary]
    risk_plan: RiskPlan
    position: PositionState | None
    action: WorkbenchAction
    ai_summary: str | None
    warnings: list[str]
