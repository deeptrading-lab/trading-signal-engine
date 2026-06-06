from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Iterable

from .models import DailyNewsScore, NewsFeature, NewsItem


ALLOWED_RISK_TAGS = {
    "earnings",
    "guidance",
    "macro",
    "fx",
    "supply_chain",
    "regulation",
    "labor",
    "geopolitics",
    "product",
    "customer",
    "sector",
    "valuation",
    "liquidity",
}


def validate_news_item(item: NewsItem) -> None:
    if not -3 <= item.sentiment_score <= 3:
        raise ValueError("sentiment_score must be between -3 and 3")
    if not 0 <= item.impact_score <= 3:
        raise ValueError("impact_score must be between 0 and 3")
    if not 0 <= item.relevance_score <= 3:
        raise ValueError("relevance_score must be between 0 and 3")
    if item.novelty not in {"NEW", "REPEAT", "UNKNOWN"}:
        raise ValueError("novelty must be NEW, REPEAT, or UNKNOWN")
    unknown_tags = set(item.risk_tags) - ALLOWED_RISK_TAGS
    if unknown_tags:
        raise ValueError(f"unknown risk tags: {sorted(unknown_tags)}")
    if not 20 <= len(item.summary_ko) <= 300:
        raise ValueError("summary_ko must be 20-300 chars")


def build_daily_news_score(symbol: str, score_date: str, items: Iterable[NewsItem]) -> DailyNewsScore:
    included: list[NewsItem] = []
    for item in items:
        validate_news_item(item)
        if item.impact_score * item.relevance_score > 0:
            included.append(item)

    weighted_scores = [item.weighted_score for item in included]
    sorted_items = sorted(included, key=lambda item: abs(item.weighted_score), reverse=True)
    risk_tags = sorted({tag for item in included for tag in item.risk_tags})
    return DailyNewsScore(
        symbol=symbol,
        date=score_date,
        item_count=len(included),
        weighted_score=float(sum(weighted_scores)),
        positive_count=sum(1 for score in weighted_scores if score > 0),
        negative_count=sum(1 for score in weighted_scores if score < 0),
        high_impact_count=sum(1 for item in included if item.impact_score >= 3 and item.relevance_score >= 2),
        negative_shock_count=sum(
            1
            for item in included
            if item.sentiment_score <= -2 and item.impact_score >= 2 and item.relevance_score >= 2
        ),
        top_summaries=tuple(item.summary_ko for item in sorted_items[:3]),
        risk_tags=tuple(risk_tags),
    )


def build_news_feature(symbol: str, daily_scores: Iterable[DailyNewsScore], *, as_of: str | None = None) -> NewsFeature:
    ordered = sorted(daily_scores, key=lambda item: item.date, reverse=True)[:10]
    weighted_total = 0.0
    negative_shocks = 0
    high_impact = 0
    summaries: list[str] = []
    risk_counter: Counter[str] = Counter()

    for index, score in enumerate(ordered):
        if index <= 2:
            decay = 1.0
        elif index <= 5:
            decay = 0.7
        else:
            decay = 0.4
        weighted_total += score.weighted_score * decay
        negative_shocks += score.negative_shock_count
        high_impact += score.high_impact_count
        for summary in score.top_summaries:
            if len(summaries) < 3:
                summaries.append(summary)
        risk_counter.update(score.risk_tags)

    return NewsFeature(
        symbol=symbol,
        lookback_days=len(ordered),
        news_score_10d=round(weighted_total, 2),
        negative_shock_count_10d=negative_shocks,
        high_impact_count_10d=high_impact,
        latest_summaries=tuple(summaries),
        risk_tags=tuple(tag for tag, _ in risk_counter.most_common()),
    )


def today_iso() -> str:
    return date.today().isoformat()
