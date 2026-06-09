from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from ai.market_data_engine.config import Settings
from ai.market_data_engine.kis import parse_trade_message
from ai.market_data_engine.models import MarketCandle, MarketTick
from ai.market_data_engine.server import create_app
from ai.market_data_engine.stream import (
    MarketStreamService,
    MinuteCandleAggregator,
    StreamBroadcaster,
)


class MemoryRepository:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict[str, Any]]] = {
            "instruments": [],
            "external_analyses": [],
            "market_ticks": [],
            "market_candles": [],
        }

    async def list_rows(self, table: str, *, filters=None, limit=100, order=None):
        rows = self.tables[table]
        if filters:
            rows = [
                row
                for row in rows
                if all(str(row.get(key)).lower() == str(value).lower() for key, value in filters.items())
            ]
        return rows[:limit]

    async def get_row(self, table: str, key: str, value: str):
        return next((row for row in self.tables[table] if row.get(key) == value), None)

    async def create_row(self, table: str, row: dict[str, Any]):
        self.tables[table].append(dict(row))
        return dict(row)

    async def update_row(self, table: str, key: str, value: str, changes: dict[str, Any]):
        row = await self.get_row(table, key, value)
        if row:
            row.update(changes)
        return row

    async def delete_row(self, table: str, key: str, value: str):
        row = await self.get_row(table, key, value)
        if not row:
            return False
        self.tables[table].remove(row)
        return True

    async def insert_ticks(self, ticks: list[MarketTick]):
        self.tables["market_ticks"].extend(
            tick.model_dump(mode="json") for tick in ticks
        )

    async def upsert_candles(self, candles: list[MarketCandle]):
        self.tables["market_candles"] = [item.model_dump(mode="json") for item in candles]


class FakeKISClient:
    async def fetch_candles(self, symbol: str, interval: str, **_: Any):
        return [
            MarketCandle(
                symbol=symbol,
                interval=interval,
                opened_at=datetime(2026, 6, 9, tzinfo=timezone.utc),
                open=100,
                high=110,
                low=90,
                close=105,
                volume=1234,
            )
        ]


def make_client() -> TestClient:
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_secret_key="sb_secret_test",
        engine_write_token="write-secret",
    )
    return TestClient(create_app(settings, MemoryRepository(), FakeKISClient()))


def test_health_has_no_analysis_runtime() -> None:
    with make_client() as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "market-data-engine"
    assert response.json()["stream"]["enabled"] is False


def test_analysis_crud_keeps_payload_opaque() -> None:
    headers = {"Authorization": "Bearer write-secret"}
    payload = {
        "symbol": "005930",
        "analysis_type": "news",
        "source": "news-service",
        "payload": {"sentiment": {"custom": [1, 2, 3]}},
    }
    with make_client() as client:
        unauthorized = client.post("/api/v1/analyses", json=payload)
        created = client.post("/api/v1/analyses", json=payload, headers=headers)
        fetched = client.get(f"/api/v1/analyses/{created.json()['id']}")
        deleted = client.delete(
            f"/api/v1/analyses/{created.json()['id']}", headers=headers
        )
    assert unauthorized.status_code == 401
    assert created.status_code == 201
    assert fetched.json()["payload"] == payload["payload"]
    assert deleted.status_code == 204


def test_candle_sync_persists_normalized_candles() -> None:
    with make_client() as client:
        response = client.post(
            "/api/v1/candles/sync",
            json={"symbol": "005930", "interval": "1w"},
            headers={"Authorization": "Bearer write-secret"},
        )
    assert response.status_code == 200
    assert response.json() == {"symbol": "005930", "interval": "1w", "count": 1}


def test_market_websocket_requires_token_and_receives_events() -> None:
    client = make_client()
    with client:
        with client.websocket_connect("/ws/market?token=write-secret") as websocket:
            assert client.portal is not None
            client.portal.call(
                client.app.state.broadcaster.publish,
                {"type": "market.tick", "tick": {"symbol": "005930"}},
            )
            assert websocket.receive_json()["type"] == "market.tick"


def test_trade_message_and_minute_aggregation() -> None:
    row = [
        "005930",
        "093001",
        "70000",
        "2",
        "100",
        "0.1",
        "69900",
        "69500",
        "70500",
        "69000",
        "70000",
        "69900",
        "3",
        "1003",
        "70000000",
        "1",
        "2",
        "1",
        "120.0",
        "500",
        "600",
        "0",
        "55.0",
        "100.0",
        "090000",
        "2",
        "500",
        "093000",
        "2",
        "500",
        "091000",
        "5",
        "500",
        "20260609",
        "0",
        "N",
        "100",
        "100",
        "1000",
        "1000",
        "0.5",
        "900",
        "10.0",
        "0",
        "2",
        "69900",
    ]
    ticks = parse_trade_message(f"0|H0STCNT0|1|{'^'.join(row)}")
    assert len(ticks) == 1
    aggregator = MinuteCandleAggregator()
    first = aggregator.add(ticks[0])
    second = aggregator.add(
        ticks[0].model_copy(update={"price": 70100, "trade_volume": 2})
    )
    assert first.open == 70000
    assert second.high == 70100
    assert second.close == 70100
    assert second.volume == 5


def test_stream_writer_batches_tick_and_candle_persistence() -> None:
    async def scenario() -> None:
        repository = MemoryRepository()
        service = MarketStreamService(
            repository,
            FakeKISClient(),
            StreamBroadcaster(),
            ("005930",),
        )
        tick = MarketTick(
            symbol="005930",
            occurred_at=datetime(2026, 6, 9, 0, 0, 1, tzinfo=timezone.utc),
            price=70000,
            trade_volume=3,
        )
        candle = service.aggregator.add(tick)
        writer = asyncio.create_task(service._write_batches())
        await service._queue.put((tick, candle))
        await service._queue.join()
        writer.cancel()
        await asyncio.gather(writer, return_exceptions=True)
        assert len(repository.tables["market_ticks"]) == 1
        assert len(repository.tables["market_candles"]) == 1

    asyncio.run(scenario())
