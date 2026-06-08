from __future__ import annotations

from dataclasses import dataclass

from .models import DailyNewsScore, NewsItem
from .news import build_daily_news_score, today_iso, validate_news_item
from .repository import NewsRepository, news_item_id
from .watchlist import require_watchlist_symbol


class NewsProviderError(RuntimeError):
    pass


class NewsProvider:
    def fetch_news_items(self, symbol: str) -> list[NewsItem]:
        raise NotImplementedError


@dataclass(frozen=True)
class IngestionResult:
    symbol: str
    score_date: str
    item_count: int
    daily_score: DailyNewsScore


class NewsIngestionService:
    def __init__(self, repository: NewsRepository, provider: NewsProvider) -> None:
        self.repository = repository
        self.provider = provider

    def ingest_symbol(self, symbol: str, *, score_date: str | None = None) -> IngestionResult:
        watch = require_watchlist_symbol(symbol)
        target_date = score_date or today_iso()
        items = self.provider.fetch_news_items(watch.symbol)
        normalized_items = _dedupe_items([
            NewsItem(
                symbol=watch.symbol,
                title=item.title,
                summary_ko=item.summary_ko,
                sentiment_score=item.sentiment_score,
                impact_score=item.impact_score,
                relevance_score=item.relevance_score,
                source=item.source,
                url=item.url,
                published_at=item.published_at,
                novelty=item.novelty,
                risk_tags=item.risk_tags,
                confidence=item.confidence,
                collected_at=item.collected_at or f"{target_date}T00:00:00+09:00",
                prompt_version=item.prompt_version,
                model=item.model,
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
                estimated_cost_usd=item.estimated_cost_usd,
            )
            for item in items
        ])
        for item in normalized_items:
            validate_news_item(item)
        daily_score = build_daily_news_score(watch.symbol, target_date, normalized_items)
        self.repository.upsert_news_items(normalized_items)
        self.repository.upsert_daily_news_score(daily_score)
        return IngestionResult(
            symbol=watch.symbol,
            score_date=target_date,
            item_count=len(normalized_items),
            daily_score=daily_score,
        )


def _dedupe_items(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    deduped: list[NewsItem] = []
    for item in items:
        keys = {
            news_item_id(item),
            _normalize_dedupe_key(item.title),
            _normalize_dedupe_key(item.summary_ko),
        }
        if seen & keys:
            continue
        seen.update(keys)
        deduped.append(item)
    return deduped


def _normalize_dedupe_key(value: str) -> str:
    return " ".join(value.strip().lower().split())
