from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Confidence(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class NewsItem:
    symbol: str
    title: str
    summary_ko: str
    sentiment_score: int
    impact_score: int
    relevance_score: int
    source: str = ""
    url: str = ""
    published_at: str | None = None
    novelty: str = "UNKNOWN"
    risk_tags: tuple[str, ...] = ()
    confidence: Confidence = Confidence.MEDIUM
    collected_at: str | None = None
    prompt_version: str = "news-v1"
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost_usd: float | None = None

    @property
    def weighted_score(self) -> int:
        return self.sentiment_score * self.impact_score * self.relevance_score


@dataclass(frozen=True)
class DailyNewsScore:
    symbol: str
    date: str
    item_count: int
    weighted_score: float
    positive_count: int
    negative_count: int
    high_impact_count: int
    negative_shock_count: int
    top_summaries: tuple[str, ...]
    risk_tags: tuple[str, ...]


@dataclass(frozen=True)
class NewsFeature:
    symbol: str
    lookback_days: int
    news_score_10d: float
    negative_shock_count_10d: int
    high_impact_count_10d: int
    latest_summaries: tuple[str, ...]
    risk_tags: tuple[str, ...]
