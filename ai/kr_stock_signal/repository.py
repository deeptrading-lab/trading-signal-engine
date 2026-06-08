from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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
    item_date = item.published_at or (item.collected_at or "")[:10]
    if not item.url and not item_date:
        raise ValueError("URL-less news items require published_at or collected_at")
    key = "|".join(
        [
            item.symbol,
            (item.url or item.title).strip().lower(),
            item_date,
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


class NewsRepository(Protocol):
    def initialize(self) -> None: ...

    def upsert_news_items(self, items: Iterable[NewsItem]) -> None: ...

    def upsert_daily_news_score(self, score: DailyNewsScore) -> None: ...

    def fetch_daily_news_scores(self, symbol: str, *, limit: int = 10) -> list[DailyNewsScore]: ...


class SupabaseRepository:
    def __init__(self, url: str, secret_key: str, *, timeout: float = 15.0) -> None:
        self.url = url.rstrip("/")
        self.secret_key = secret_key
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "SupabaseRepository":
        url = os.getenv("SUPABASE_URL", "").strip()
        secret_key = (
            os.getenv("SUPABASE_SECRET_KEY", "").strip()
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        if not url:
            raise ValueError("SUPABASE_URL is not configured")
        if not secret_key:
            raise ValueError("SUPABASE_SECRET_KEY is not configured")
        if secret_key.startswith("sb_publishable_"):
            raise ValueError("Supabase publishable key cannot be used for backend writes")
        return cls(url, secret_key)

    def initialize(self) -> None:
        rows = [
            {
                "symbol": item.symbol,
                "name_ko": item.name_ko,
                "market": item.market,
                "enabled": True,
            }
            for item in WATCHLIST.values()
        ]
        self._request(
            "watchlist_symbols",
            method="POST",
            payload=rows,
            query={"on_conflict": "symbol"},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def upsert_news_items(self, items: Iterable[NewsItem]) -> None:
        rows = [
            {
                "id": news_item_id(item),
                "symbol": item.symbol,
                "published_at": item.published_at,
                "source": item.source,
                "title": item.title,
                "url": item.url,
                "summary_ko": item.summary_ko,
                "sentiment_score": item.sentiment_score,
                "impact_score": item.impact_score,
                "relevance_score": item.relevance_score,
                "novelty": item.novelty,
                "risk_tags": list(item.risk_tags),
                "confidence": item.confidence.value,
                "collected_at": item.collected_at or datetime.now(timezone.utc).isoformat(),
                "prompt_version": item.prompt_version,
                "model": item.model,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "estimated_cost_usd": item.estimated_cost_usd,
            }
            for item in items
        ]
        if not rows:
            return
        self._request(
            "news_items",
            method="POST",
            payload=rows,
            query={"on_conflict": "id"},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def upsert_daily_news_score(self, score: DailyNewsScore) -> None:
        self._request(
            "daily_news_scores",
            method="POST",
            payload=[
                {
                    "symbol": score.symbol,
                    "date": score.date,
                    "item_count": score.item_count,
                    "weighted_score": score.weighted_score,
                    "positive_count": score.positive_count,
                    "negative_count": score.negative_count,
                    "high_impact_count": score.high_impact_count,
                    "negative_shock_count": score.negative_shock_count,
                    "top_summaries": list(score.top_summaries),
                    "risk_tags": list(score.risk_tags),
                }
            ],
            query={"on_conflict": "symbol,date"},
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def fetch_daily_news_scores(self, symbol: str, *, limit: int = 10) -> list[DailyNewsScore]:
        rows = self._request(
            "daily_news_scores",
            query={
                "select": "*",
                "symbol": f"eq.{symbol}",
                "order": "date.desc",
                "limit": str(limit),
            },
        )
        return [
            DailyNewsScore(
                symbol=str(row["symbol"]),
                date=str(row["date"]),
                item_count=int(row["item_count"]),
                weighted_score=float(row["weighted_score"]),
                positive_count=int(row["positive_count"]),
                negative_count=int(row["negative_count"]),
                high_impact_count=int(row["high_impact_count"]),
                negative_shock_count=int(row["negative_shock_count"]),
                top_summaries=tuple(row.get("top_summaries") or ()),
                risk_tags=tuple(row.get("risk_tags") or ()),
            )
            for row in rows
        ]

    def _request(
        self,
        table: str,
        *,
        method: str = "GET",
        payload: object | None = None,
        query: dict[str, str] | None = None,
        prefer: str | None = None,
    ) -> list[dict[str, object]]:
        endpoint = f"{self.url}/rest/v1/{table}"
        if query:
            endpoint = f"{endpoint}?{urlencode(query)}"
        headers = {
            "apikey": self.secret_key,
            "Accept": "application/json",
        }
        if not self.secret_key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.secret_key}"
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        request = Request(endpoint, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase request failed ({error.code}): {detail}") from error
        except URLError as error:
            raise RuntimeError(f"Supabase request failed: {error.reason}") from error
        if not raw:
            return []
        decoded = json.loads(raw.decode("utf-8"))
        if not isinstance(decoded, list):
            raise RuntimeError("Supabase response must be a JSON array")
        return decoded


def create_repository_from_env() -> NewsRepository:
    backend = os.getenv("KR_STOCK_DB_BACKEND", "sqlite").strip().lower()
    if backend == "sqlite":
        path = os.getenv("KR_STOCK_SQLITE_PATH", "data/kr_stock_news.db")
        return KrStockRepository(path)
    if backend == "supabase":
        return SupabaseRepository.from_env()
    raise ValueError("KR_STOCK_DB_BACKEND must be sqlite or supabase")
