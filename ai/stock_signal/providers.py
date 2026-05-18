from __future__ import annotations

import csv
import io
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from .models import PriceBar


class PriceProviderError(RuntimeError):
    pass


class YahooChartPriceProvider:
    """Free Yahoo chart endpoint. No API key, best effort only."""

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_daily(self, ticker: str) -> list[PriceBar]:
        normalized = ticker.strip().upper()
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{normalized}?range=1y&interval=1d"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as error:
            raise PriceProviderError(f"yahoo provider unavailable: {error}") from error

        try:
            result = payload["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError) as error:
            raise PriceProviderError("yahoo provider returned an unexpected payload") from error

        bars: list[PriceBar] = []
        for index, timestamp in enumerate(timestamps):
            try:
                open_price = quote["open"][index]
                high = quote["high"][index]
                low = quote["low"][index]
                close = quote["close"][index]
                volume = quote["volume"][index]
            except (IndexError, KeyError, TypeError) as error:
                raise PriceProviderError("yahoo provider returned incomplete arrays") from error

            if None in (open_price, high, low, close, volume):
                continue

            bars.append(
                PriceBar(
                    date=datetime.fromtimestamp(timestamp, tz=timezone.utc).date().isoformat(),
                    open=float(open_price),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=int(volume),
                )
            )

        if len(bars) < 60:
            raise PriceProviderError("yahoo provider returned too few rows")
        return bars


class StooqPriceProvider:
    """Free daily OHLCV provider. Requires STOOQ_API_KEY after captcha setup."""

    def __init__(self, *, timeout_seconds: float = 8.0, api_key: str | None = None) -> None:
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key if api_key is not None else os.getenv("STOOQ_API_KEY")

    def fetch_daily(self, ticker: str) -> list[PriceBar]:
        if not self.api_key:
            raise PriceProviderError("STOOQ_API_KEY is not configured")

        symbol = _to_stooq_symbol(ticker)
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d&apikey={self.api_key}"
        try:
            with urlopen(url, timeout=self.timeout_seconds) as response:
                payload = response.read().decode("utf-8")
        except (OSError, URLError) as error:
            raise PriceProviderError(f"price provider unavailable: {error}") from error

        bars = _parse_stooq_csv(payload)
        if len(bars) < 60:
            raise PriceProviderError("price provider returned too few rows")
        return bars


class SyntheticPriceProvider:
    """Deterministic fallback so the MVP can be checked without network or API keys."""

    def fetch_daily(self, ticker: str) -> list[PriceBar]:
        seed = sum(ord(char) for char in ticker.upper())
        base = 80.0 + (seed % 90)
        today = date.today()
        bars: list[PriceBar] = []
        price = base

        for index in range(260):
            drift = 0.0009 + ((seed % 7) - 3) * 0.00008
            cycle = math.sin(index / 12.0 + seed) * 0.009
            shock = math.sin(index / 5.0 + seed * 0.1) * 0.004
            price = max(5.0, price * (1.0 + drift + cycle + shock))
            high = price * (1.0 + 0.008 + abs(math.sin(index)) * 0.006)
            low = price * (1.0 - 0.008 - abs(math.cos(index)) * 0.006)
            open_price = (high + low) / 2.0
            volume = int(1_000_000 + (seed % 20) * 50_000 + abs(math.sin(index / 4.0)) * 700_000)
            bars.append(
                PriceBar(
                    date=(today - timedelta(days=260 - index)).isoformat(),
                    open=round(open_price, 2),
                    high=round(high, 2),
                    low=round(low, 2),
                    close=round(price, 2),
                    volume=volume,
                )
            )

        return bars


def _to_stooq_symbol(ticker: str) -> str:
    normalized = ticker.strip().lower()
    if "." not in normalized:
        return f"{normalized}.us"
    return normalized


def _parse_stooq_csv(payload: str) -> list[PriceBar]:
    reader = csv.DictReader(io.StringIO(payload))
    bars: list[PriceBar] = []
    for row in reader:
        if row.get("Close") in (None, "No data"):
            continue
        try:
            bars.append(
                PriceBar(
                    date=row["Date"],
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(float(row["Volume"])),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return bars
