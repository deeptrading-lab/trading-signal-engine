from __future__ import annotations

import json
import threading
from datetime import date, timedelta
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

import pytest

from ai.kr_stock_signal.models import DailyNewsScore, NewsItem
from ai.kr_stock_signal.news import build_daily_news_score, build_news_feature, validate_news_item
from ai.kr_stock_signal.ingestion import NewsIngestionService, NewsProvider
from ai.kr_stock_signal.openai_news import _items_from_payload
from ai.kr_stock_signal.repository import (
    KrStockRepository,
    SupabaseRepository,
    create_repository_from_env,
    news_item_id,
)
from ai.kr_stock_signal.server import KrStockNewsHandler
from ai.kr_stock_signal.watchlist import WATCHLIST, require_watchlist_symbol


class FakeNewsProvider(NewsProvider):
    def fetch_news_items(self, symbol: str) -> list[NewsItem]:
        return [
            NewsItem(
                symbol=symbol,
                title="삼성전자 HBM 공급 기대",
                summary_ko="삼성전자 HBM 공급 기대가 커지며 투자심리에 긍정적으로 작용할 수 있습니다.",
                sentiment_score=2,
                impact_score=3,
                relevance_score=3,
                source="example",
                url="https://example.com/hbm",
                published_at="2026-06-06",
                risk_tags=("sector",),
            ),
            NewsItem(
                symbol=symbol,
                title="삼성전자 HBM 공급 기대",
                summary_ko="삼성전자 HBM 공급 기대가 커지며 투자심리에 긍정적으로 작용할 수 있습니다.",
                sentiment_score=2,
                impact_score=3,
                relevance_score=3,
                source="example",
                url="https://example.com/hbm",
                published_at="2026-06-06",
                risk_tags=("sector",),
            ),
        ]


def test_watchlist_accepts_initial_three_symbols_and_rejects_others():
    assert set(WATCHLIST) == {"005930.KS", "000660.KS", "005380.KS"}
    assert require_watchlist_symbol("삼성전자").symbol == "005930.KS"
    with pytest.raises(ValueError, match="watchlist 등록 필요"):
        require_watchlist_symbol("AAPL")


def test_news_item_validation_and_daily_score_aggregation():
    items = [
        NewsItem(
            symbol="005930.KS",
            title="삼성전자 실적 개선",
            summary_ko="삼성전자 실적 개선 기대가 커졌다는 당일 뉴스입니다.",
            sentiment_score=2,
            impact_score=3,
            relevance_score=3,
            risk_tags=("earnings",),
        ),
        NewsItem(
            symbol="005930.KS",
            title="시장 잡음",
            summary_ko="시장 전체 변동성에 대한 낮은 관련도의 뉴스입니다.",
            sentiment_score=-1,
            impact_score=0,
            relevance_score=3,
        ),
    ]
    score = build_daily_news_score("005930.KS", "2026-06-06", items)
    assert score.item_count == 1
    assert score.weighted_score == 18
    assert score.positive_count == 1
    assert score.high_impact_count == 1
    assert score.top_summaries == ("삼성전자 실적 개선 기대가 커졌다는 당일 뉴스입니다.",)

    invalid = NewsItem(
        symbol="005930.KS",
        title="bad",
        summary_ko="짧음",
        sentiment_score=4,
        impact_score=1,
        relevance_score=1,
    )
    with pytest.raises(ValueError):
        validate_news_item(invalid)


def test_news_feature_uses_recent_10_scores_without_raw_reanalysis():
    scores = [
        DailyNewsScore(
            symbol="005930.KS",
            date=(date.today() - timedelta(days=index)).isoformat(),
            item_count=1,
            weighted_score=10.0,
            positive_count=1,
            negative_count=0,
            high_impact_count=1,
            negative_shock_count=0,
            top_summaries=(f"요약 {index}",),
            risk_tags=("sector",),
        )
        for index in range(12)
    ]
    feature = build_news_feature("005930.KS", scores)
    assert feature.lookback_days == 10
    assert feature.news_score_10d == 67.0
    assert feature.high_impact_count_10d == 10
    assert feature.latest_summaries == ("요약 0", "요약 1", "요약 2")


def test_repository_initializes_schema_seeds_watchlist_and_upserts(tmp_path):
    repo = KrStockRepository(tmp_path / "signal.db")
    repo.initialize()
    item = NewsItem(
        symbol="005930.KS",
        title="삼성전자 신규 수주",
        summary_ko="삼성전자 신규 수주가 투자심리에 긍정적으로 작용할 수 있습니다.",
        sentiment_score=1,
        impact_score=2,
        relevance_score=3,
        url="https://example.com/news/1",
        published_at="2026-06-06",
    )
    first_id = news_item_id(item)
    repo.upsert_news_items([item])
    repo.upsert_news_items([item])
    daily = build_daily_news_score("005930.KS", "2026-06-06", [item])
    repo.upsert_daily_news_score(daily)
    fetched = repo.fetch_daily_news_scores("005930.KS")
    assert first_id == news_item_id(item)
    assert fetched[0].weighted_score == 6
    with repo.connect() as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            ).fetchall()
        }
    assert {"watchlist_symbols", "news_items", "daily_news_scores"} <= table_names
    assert "price_bars" not in table_names
    assert "signal_reports" not in table_names


def test_news_ingestion_service_persists_items_and_daily_score(tmp_path):
    repo = KrStockRepository(tmp_path / "signal.db")
    repo.initialize()
    service = NewsIngestionService(repo, FakeNewsProvider())
    result = service.ingest_symbol("삼성전자", score_date="2026-06-06")
    assert result.symbol == "005930.KS"
    assert result.item_count == 1
    fetched = repo.fetch_daily_news_scores("005930.KS")
    assert fetched[0].weighted_score == 18
    assert fetched[0].top_summaries == ("삼성전자 HBM 공급 기대가 커지며 투자심리에 긍정적으로 작용할 수 있습니다.",)


def test_openai_news_payload_mapping_is_schema_validated_by_news_layer():
    items = _items_from_payload(
        {
            "symbol": "005930.KS",
            "items": [
                {
                    "title": "삼성전자 실적 기대",
                    "source": "example",
                    "url": "https://example.com/1",
                    "published_at": "2026-06-06",
                    "summary_ko": "삼성전자 실적 기대가 커지며 반도체 업황 개선 가능성이 언급됐습니다.",
                    "sentiment_score": 2,
                    "impact_score": 2,
                    "relevance_score": 3,
                    "novelty": "NEW",
                    "risk_tags": ["earnings", "market_volatility"],
                    "confidence": "MEDIUM",
                }
            ],
        },
        expected_symbol="005930.KS",
        model="gpt-test",
        input_tokens=100,
        output_tokens=50,
    )
    validate_news_item(items[0])
    assert items[0].model == "gpt-test"
    assert items[0].input_tokens == 100
    assert items[0].risk_tags == ("earnings",)


class FakeHTTPResponse:
    def __init__(self, payload: object | None = None) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        if self.payload is None:
            return b""
        return json.dumps(self.payload).encode("utf-8")


def test_supabase_repository_uses_backend_secret_and_postgrest_upsert(monkeypatch):
    requests = []

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeHTTPResponse()

    monkeypatch.setattr("ai.kr_stock_signal.repository.urlopen", fake_urlopen)
    repo = SupabaseRepository("https://project.supabase.co", "sb_secret_test")
    repo.initialize()
    item = NewsItem(
        symbol="005930.KS",
        title="삼성전자 신규 수주",
        summary_ko="삼성전자 신규 수주가 투자심리에 긍정적으로 작용할 수 있습니다.",
        sentiment_score=1,
        impact_score=2,
        relevance_score=3,
        published_at="2026-06-06",
    )
    repo.upsert_news_items([item])
    repo.upsert_daily_news_score(build_daily_news_score("005930.KS", "2026-06-06", [item]))

    assert len(requests) == 3
    news_request = requests[1][0]
    assert news_request.full_url.endswith("/rest/v1/news_items?on_conflict=id")
    assert news_request.headers["Apikey"] == "sb_secret_test"
    assert "Authorization" not in news_request.headers
    payload = json.loads(news_request.data.decode("utf-8"))
    assert payload[0]["id"] == news_item_id(item)
    assert payload[0]["collected_at"]


def test_supabase_repository_maps_daily_scores_and_rejects_publishable_key(monkeypatch):
    rows = [
        {
            "symbol": "005930.KS",
            "date": "2026-06-06",
            "item_count": 1,
            "weighted_score": 18,
            "positive_count": 1,
            "negative_count": 0,
            "high_impact_count": 1,
            "negative_shock_count": 0,
            "top_summaries": ["핵심 요약"],
            "risk_tags": ["sector"],
        }
    ]
    monkeypatch.setattr(
        "ai.kr_stock_signal.repository.urlopen",
        lambda request, timeout: FakeHTTPResponse(rows),
    )
    scores = SupabaseRepository(
        "https://project.supabase.co",
        "sb_secret_test",
    ).fetch_daily_news_scores("005930.KS")
    assert scores[0].weighted_score == 18
    assert scores[0].top_summaries == ("핵심 요약",)

    monkeypatch.setenv("KR_STOCK_DB_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_publishable_test")
    with pytest.raises(ValueError, match="publishable key"):
        create_repository_from_env()


def test_supabase_legacy_service_role_key_uses_bearer_header(monkeypatch):
    requests = []
    monkeypatch.setattr(
        "ai.kr_stock_signal.repository.urlopen",
        lambda request, timeout: requests.append(request) or FakeHTTPResponse([]),
    )
    SupabaseRepository(
        "https://project.supabase.co",
        "legacy.jwt.service-role",
    ).fetch_daily_news_scores("005930.KS")
    assert requests[0].headers["Authorization"] == "Bearer legacy.jwt.service-role"


def test_kr_stock_news_http_api_refresh_daily_and_feature(tmp_path):
    repo = KrStockRepository(tmp_path / "api.db")
    repo.initialize()
    KrStockNewsHandler.repository = repo
    server = ThreadingHTTPServer(("127.0.0.1", 0), KrStockNewsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        refresh = Request(
            f"{base_url}/api/kr-stocks/news/refresh",
            data=json.dumps(
                {
                    "symbol": "삼성전자",
                    "provider": "sample",
                    "score_date": "2026-06-06",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(refresh) as response:
            assert response.status == 201

        with urlopen(
            f"{base_url}/api/kr-stocks/news/daily?symbol=005930.KS&date=2026-06-06"
        ) as response:
            daily = json.loads(response.read().decode("utf-8"))
        assert daily["scores"][0]["weighted_score"] == 6.0

        with urlopen(
            f"{base_url}/api/kr-stocks/news/feature?symbol=005930.KS&lookback_days=10"
        ) as response:
            feature = json.loads(response.read().decode("utf-8"))
        assert feature["news_score_10d"] == 6.0
        assert feature["lookback_days"] == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
