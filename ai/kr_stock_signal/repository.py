from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import DailyNewsScore, NewsItem
from .watchlist import WATCHLIST


SCHEMA_SQL = """
create table if not exists watchlist_symbols (
    symbol text primary key,
    name_ko text not null,
    market text not null,
    enabled integer not null,
    created_at text not null
);

create table if not exists news_items (
    id text primary key,
    symbol text not null,
    published_at text,
    source text,
    title text not null,
    url text,
    summary_ko text not null,
    sentiment_score integer not null,
    impact_score integer not null,
    relevance_score integer not null,
    novelty text not null,
    risk_tags_json text not null,
    confidence text not null,
    collected_at text not null,
    prompt_version text not null,
    model text,
    input_tokens integer,
    output_tokens integer,
    estimated_cost_usd real
);

create table if not exists daily_news_scores (
    symbol text not null,
    date text not null,
    item_count integer not null,
    weighted_score real not null,
    positive_count integer not null,
    negative_count integer not null,
    high_impact_count integer not null,
    negative_shock_count integer not null,
    top_summaries_json text not null,
    risk_tags_json text not null,
    primary key(symbol, date)
);
"""


def news_item_id(item: NewsItem) -> str:
    key = "|".join(
        [
            item.symbol,
            (item.url or item.title).strip().lower(),
            item.published_at or "",
        ]
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class KrStockRepository:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SCHEMA_SQL)
            self.seed_watchlist(connection)

    def seed_watchlist(self, connection: sqlite3.Connection | None = None) -> None:
        owns_connection = connection is None
        conn = connection or self.connect()
        try:
            for item in WATCHLIST.values():
                conn.execute(
                    """
                    insert into watchlist_symbols(symbol, name_ko, market, enabled, created_at)
                    values (?, ?, ?, 1, datetime('now'))
                    on conflict(symbol) do update set
                        name_ko = excluded.name_ko,
                        market = excluded.market,
                        enabled = excluded.enabled
                    """,
                    (item.symbol, item.name_ko, item.market),
                )
            conn.commit()
        finally:
            if owns_connection:
                conn.close()

    def upsert_news_items(self, items: Iterable[NewsItem]) -> None:
        with self.connect() as connection:
            connection.executemany(
                """
                insert into news_items(
                    id, symbol, published_at, source, title, url, summary_ko,
                    sentiment_score, impact_score, relevance_score, novelty,
                    risk_tags_json, confidence, collected_at, prompt_version,
                    model, input_tokens, output_tokens, estimated_cost_usd
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, coalesce(?, datetime('now')), ?, ?, ?, ?, ?)
                on conflict(id) do update set
                    summary_ko = excluded.summary_ko,
                    sentiment_score = excluded.sentiment_score,
                    impact_score = excluded.impact_score,
                    relevance_score = excluded.relevance_score,
                    novelty = excluded.novelty,
                    risk_tags_json = excluded.risk_tags_json,
                    confidence = excluded.confidence
                """,
                [
                    (
                        news_item_id(item),
                        item.symbol,
                        item.published_at,
                        item.source,
                        item.title,
                        item.url,
                        item.summary_ko,
                        item.sentiment_score,
                        item.impact_score,
                        item.relevance_score,
                        item.novelty,
                        json.dumps(list(item.risk_tags), ensure_ascii=False),
                        item.confidence.value,
                        item.collected_at,
                        item.prompt_version,
                        item.model,
                        item.input_tokens,
                        item.output_tokens,
                        item.estimated_cost_usd,
                    )
                    for item in items
                ],
            )

    def upsert_daily_news_score(self, score: DailyNewsScore) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                insert into daily_news_scores(
                    symbol, date, item_count, weighted_score, positive_count, negative_count,
                    high_impact_count, negative_shock_count, top_summaries_json, risk_tags_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(symbol, date) do update set
                    item_count = excluded.item_count,
                    weighted_score = excluded.weighted_score,
                    positive_count = excluded.positive_count,
                    negative_count = excluded.negative_count,
                    high_impact_count = excluded.high_impact_count,
                    negative_shock_count = excluded.negative_shock_count,
                    top_summaries_json = excluded.top_summaries_json,
                    risk_tags_json = excluded.risk_tags_json
                """,
                (
                    score.symbol,
                    score.date,
                    score.item_count,
                    score.weighted_score,
                    score.positive_count,
                    score.negative_count,
                    score.high_impact_count,
                    score.negative_shock_count,
                    json.dumps(list(score.top_summaries), ensure_ascii=False),
                    json.dumps(list(score.risk_tags), ensure_ascii=False),
                ),
            )

    def fetch_daily_news_scores(self, symbol: str, *, limit: int = 10) -> list[DailyNewsScore]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                select * from daily_news_scores
                where symbol = ?
                order by date desc
                limit ?
                """,
                (symbol, limit),
            ).fetchall()
        return [
            DailyNewsScore(
                symbol=row["symbol"],
                date=row["date"],
                item_count=int(row["item_count"]),
                weighted_score=float(row["weighted_score"]),
                positive_count=int(row["positive_count"]),
                negative_count=int(row["negative_count"]),
                high_impact_count=int(row["high_impact_count"]),
                negative_shock_count=int(row["negative_shock_count"]),
                top_summaries=tuple(json.loads(row["top_summaries_json"])),
                risk_tags=tuple(json.loads(row["risk_tags_json"])),
            )
            for row in rows
        ]
