from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from .models import MarketFlowSnapshot, PriceBar


class PriceProviderError(RuntimeError):
    pass


class BitcoinPriceProvider:
    """Free Yahoo chart endpoint for BTC-USD. No API key, best effort only."""

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_daily(self, symbol: str = "BTC") -> list[PriceBar]:
        if symbol.strip().upper() not in {"BTC", "BTC-USD", "BITCOIN"}:
            raise PriceProviderError("Bitcoin provider only supports BTC")

        url = "https://query1.finance.yahoo.com/v8/finance/chart/BTC-USD?range=1y&interval=1d"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as error:
            raise PriceProviderError(f"bitcoin price provider unavailable: {error}") from error

        try:
            result = payload["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError) as error:
            raise PriceProviderError("bitcoin price provider returned an unexpected payload") from error

        bars: list[PriceBar] = []
        for index, timestamp in enumerate(timestamps):
            try:
                open_price = quote["open"][index]
                high = quote["high"][index]
                low = quote["low"][index]
                close = quote["close"][index]
                volume = quote["volume"][index]
            except (IndexError, KeyError, TypeError) as error:
                raise PriceProviderError("bitcoin price provider returned incomplete arrays") from error

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
            raise PriceProviderError("bitcoin price provider returned too few rows")
        return bars


class SyntheticBitcoinPriceProvider:
    """Deterministic BTC-like fallback so local checks work without network access."""

    def fetch_daily(self, symbol: str = "BTC") -> list[PriceBar]:
        if symbol.strip().upper() not in {"BTC", "BTC-USD", "BITCOIN"}:
            raise PriceProviderError("synthetic Bitcoin provider only supports BTC")

        today = date.today()
        bars: list[PriceBar] = []
        price = 62_000.0

        for index in range(260):
            drift = 0.0012
            cycle = math.sin(index / 14.0) * 0.014
            shock = math.sin(index / 5.0) * 0.008
            price = max(12_000.0, price * (1.0 + drift + cycle + shock))
            high = price * (1.0 + 0.012 + abs(math.sin(index)) * 0.009)
            low = price * (1.0 - 0.012 - abs(math.cos(index)) * 0.009)
            open_price = (high + low) / 2.0
            volume = int(18_000_000_000 + abs(math.sin(index / 4.0)) * 9_000_000_000)
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


class BinanceMarketFlowProvider:
    """Public Binance market data. This is exchange flow, not full on-chain data."""

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_market_flow(self, symbol: str = "BTC") -> MarketFlowSnapshot:
        if symbol.strip().upper() not in {"BTC", "BTCUSDT", "BTC-USD", "BITCOIN"}:
            raise PriceProviderError("Binance market flow provider only supports BTC")

        ticker = self._get_json("https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT")
        hourly_klines = self._get_json("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=24")
        daily_klines = self._get_json("https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=8")
        try:
            price_change_pct = float(ticker["priceChangePercent"])
            quote_volume = float(ticker["quoteVolume"])
            taker_buy_quote_volume = sum(float(row[10]) for row in hourly_klines)
            taker_buy_ratio = taker_buy_quote_volume / quote_volume if quote_volume > 0 else None
            daily_quote_volumes = [float(row[7]) for row in daily_klines[:-1]]
        except (KeyError, TypeError, ValueError, IndexError) as error:
            raise PriceProviderError("Binance market flow provider returned an unexpected payload") from error

        seven_day_avg = sum(daily_quote_volumes) / len(daily_quote_volumes) if daily_quote_volumes else None
        volume_vs_7d = quote_volume / seven_day_avg if seven_day_avg and seven_day_avg > 0 else None
        return MarketFlowSnapshot(
            source="binance:BTCUSDT",
            symbol="BTCUSDT",
            price_change_pct_24h=round(price_change_pct, 2),
            quote_volume_24h=round(quote_volume, 2),
            taker_buy_quote_volume_24h=round(taker_buy_quote_volume, 2),
            taker_buy_ratio_24h=round(taker_buy_ratio, 4) if taker_buy_ratio is not None else None,
            volume_vs_7d_avg=round(volume_vs_7d, 2) if volume_vs_7d is not None else None,
            summary_ko=_market_flow_summary(price_change_pct, taker_buy_ratio, volume_vs_7d),
        )

    def _get_json(self, url: str) -> object:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as error:
            raise PriceProviderError(f"Binance market flow provider unavailable: {error}") from error


def _market_flow_summary(
    price_change_pct: float,
    taker_buy_ratio: float | None,
    volume_vs_7d: float | None,
) -> str:
    direction = "상승" if price_change_pct > 0 else "하락" if price_change_pct < 0 else "보합"
    buy_pressure = "매수 우위" if taker_buy_ratio is not None and taker_buy_ratio >= 0.52 else "매도/중립 우위"
    volume_text = "거래량은 7일 평균과 비교 불가"
    if volume_vs_7d is not None:
        if volume_vs_7d >= 1.25:
            volume_text = "거래량은 7일 평균보다 높음"
        elif volume_vs_7d <= 0.75:
            volume_text = "거래량은 7일 평균보다 낮음"
        else:
            volume_text = "거래량은 7일 평균 수준"
    return f"Binance 24시간 기준 가격은 {direction}, 체결 흐름은 {buy_pressure}, {volume_text}."
