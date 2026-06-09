from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from .kis import KISClient
from .models import MarketCandle, MarketTick
from .repository import MarketDataRepository


class StreamBroadcaster:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def publish(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for client in tuple(self._clients):
            try:
                await client.send_json(payload)
            except Exception:
                stale.append(client)
        for client in stale:
            self.disconnect(client)


class MinuteCandleAggregator:
    def __init__(self) -> None:
        self._candles: dict[tuple[str, datetime], MarketCandle] = {}

    def add(self, tick: MarketTick) -> MarketCandle:
        opened_at = tick.occurred_at.replace(second=0, microsecond=0)
        key = (tick.symbol, opened_at)
        current = self._candles.get(key)
        if current is None:
            candle = MarketCandle(
                symbol=tick.symbol,
                interval="1m",
                opened_at=opened_at,
                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,
                volume=tick.trade_volume,
                source=tick.source,
            )
        else:
            candle = current.model_copy(
                update={
                    "high": max(current.high, tick.price),
                    "low": min(current.low, tick.price),
                    "close": tick.price,
                    "volume": current.volume + tick.trade_volume,
                }
            )
        self._candles[key] = candle
        self._evict_before(opened_at)
        return candle

    def _evict_before(self, current_minute: datetime) -> None:
        for key in tuple(self._candles):
            if key[1] < current_minute:
                del self._candles[key]


class MarketStreamService:
    def __init__(
        self,
        repository: MarketDataRepository,
        kis_client: KISClient,
        broadcaster: StreamBroadcaster,
        symbols: tuple[str, ...],
    ) -> None:
        self.repository = repository
        self.kis_client = kis_client
        self.broadcaster = broadcaster
        self.symbols = symbols
        self.aggregator = MinuteCandleAggregator()
        self.last_event_at: datetime | None = None
        self.last_error: str | None = None
        self.connected = False
        self._queue: asyncio.Queue[tuple[MarketTick, MarketCandle]] = asyncio.Queue(
            maxsize=10_000
        )
        self._stream_task: asyncio.Task[None] | None = None
        self._writer_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if not self._stream_task:
            self._stream_task = asyncio.create_task(self.run())
            self._writer_task = asyncio.create_task(self._write_batches())

    async def stop(self) -> None:
        tasks = [task for task in (self._stream_task, self._writer_task) if task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._stream_task = None
        self._writer_task = None

    async def run(self) -> None:
        delay = 1
        while True:
            try:
                self.connected = True
                async for tick in self.kis_client.stream_ticks(self.symbols):
                    self.last_event_at = tick.occurred_at
                    self.last_error = None
                    candle = self.aggregator.add(tick)
                    try:
                        self._queue.put_nowait((tick, candle))
                    except asyncio.QueueFull:
                        self.last_error = "market data persistence queue is full"
                    await self.broadcaster.publish(
                        {
                            "type": "market.tick",
                            "tick": tick.model_dump(mode="json"),
                            "candle": candle.model_dump(mode="json"),
                        }
                    )
                raise ConnectionError("KIS stream closed")
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.connected = False
                self.last_error = str(error)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    async def _write_batches(self) -> None:
        while True:
            first = await self._queue.get()
            batch = [first]
            while len(batch) < 200:
                try:
                    batch.append(await asyncio.wait_for(self._queue.get(), timeout=0.2))
                except TimeoutError:
                    break
            ticks = [tick for tick, _ in batch]
            candles = {
                (candle.symbol, candle.interval, candle.opened_at): candle
                for _, candle in batch
            }
            try:
                await self.repository.insert_ticks(ticks)
                await self.repository.upsert_candles(list(candles.values()))
            except Exception as error:
                self.last_error = str(error)
            finally:
                for _ in batch:
                    self._queue.task_done()

    def health(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "connected": self.connected,
            "symbols": list(self.symbols),
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "last_error": self.last_error,
            "queued_events": self._queue.qsize(),
        }
