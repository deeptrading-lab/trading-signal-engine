from __future__ import annotations

import json
import time as clock
from datetime import datetime, time, timezone
from typing import Any, AsyncIterator
from zoneinfo import ZoneInfo

import httpx
import websockets

from .models import MarketCandle, MarketTick

SEOUL = ZoneInfo("Asia/Seoul")
TRADE_COLUMNS = (
    "symbol",
    "trade_time",
    "price",
    "change_sign",
    "change",
    "change_rate",
    "weighted_average_price",
    "open",
    "high",
    "low",
    "ask_price",
    "bid_price",
    "trade_volume",
    "cumulative_volume",
    "cumulative_trade_amount",
    "sell_count",
    "buy_count",
    "net_buy_count",
    "trade_strength",
    "total_sell_volume",
    "total_buy_volume",
    "trade_type",
    "buy_rate",
    "volume_change_rate",
    "open_time",
    "open_change_sign",
    "open_change",
    "high_time",
    "high_change_sign",
    "high_change",
    "low_time",
    "low_change_sign",
    "low_change",
    "business_date",
    "new_market_open_code",
    "trading_halt",
    "ask_quantity",
    "bid_quantity",
    "total_ask_quantity",
    "total_bid_quantity",
    "turnover_rate",
    "prior_same_time_volume",
    "prior_same_time_volume_rate",
    "hour_code",
    "market_status",
    "vi_standard_price",
)


class KISClient:
    def __init__(
        self,
        app_key: str,
        app_secret: str,
        *,
        environment: str = "prod",
        rest_url: str = "",
        ws_url: str = "",
        timeout: float = 15.0,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.environment = environment
        self.rest_url = rest_url or (
            "https://openapi.koreainvestment.com:9443"
            if environment == "prod"
            else "https://openapivts.koreainvestment.com:29443"
        )
        self.ws_url = ws_url or (
            "ws://ops.koreainvestment.com:21000/tryitout"
            if environment == "prod"
            else "ws://ops.koreainvestment.com:31000/tryitout"
        )
        self.timeout = timeout
        self._access_token = ""
        self._access_token_expires_at = 0.0

    async def access_token(self) -> str:
        if self._access_token and clock.monotonic() < self._access_token_expires_at:
            return self._access_token
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        data = await self._post_json("/oauth2/tokenP", payload)
        self._access_token = str(data["access_token"])
        expires_in = max(int(data.get("expires_in") or 3600), 120)
        self._access_token_expires_at = clock.monotonic() + expires_in - 60
        return self._access_token

    async def approval_key(self) -> str:
        data = await self._post_json(
            "/oauth2/Approval",
            {
                "grant_type": "client_credentials",
                "appkey": self.app_key,
                "secretkey": self.app_secret,
            },
        )
        return str(data["approval_key"])

    async def fetch_candles(
        self,
        symbol: str,
        interval: str,
        *,
        start: str | None = None,
        end: str | None = None,
        hour: str | None = None,
    ) -> list[MarketCandle]:
        if interval == "1m":
            return await self._fetch_minute_candles(symbol, hour=hour)
        period = {"1d": "D", "1w": "W", "1mo": "M"}[interval]
        today = datetime.now(SEOUL).strftime("%Y%m%d")
        body = await self._get_json(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id="FHKST03010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": start or today,
                "FID_INPUT_DATE_2": end or today,
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        return [
            MarketCandle(
                symbol=symbol,
                interval=interval,
                opened_at=_parse_kis_date(str(row["stck_bsop_date"])),
                open=float(row["stck_oprc"]),
                high=float(row["stck_hgpr"]),
                low=float(row["stck_lwpr"]),
                close=float(row["stck_clpr"]),
                volume=float(row["acml_vol"]),
            )
            for row in body.get("output2", [])
        ]

    async def _fetch_minute_candles(
        self, symbol: str, *, hour: str | None = None
    ) -> list[MarketCandle]:
        body = await self._get_json(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id="FHKST03010200",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_HOUR_1": hour or datetime.now(SEOUL).strftime("%H%M%S"),
                "FID_PW_DATA_INCU_YN": "Y",
                "FID_ETC_CLS_CODE": "",
            },
        )
        business_date = datetime.now(SEOUL).strftime("%Y%m%d")
        return [
            MarketCandle(
                symbol=symbol,
                interval="1m",
                opened_at=_parse_kis_datetime(
                    str(row.get("stck_bsop_date") or business_date),
                    str(row["stck_cntg_hour"]),
                ),
                open=float(row["stck_oprc"]),
                high=float(row["stck_hgpr"]),
                low=float(row["stck_lwpr"]),
                close=float(row["stck_prpr"]),
                volume=float(row["cntg_vol"]),
            )
            for row in body.get("output2", [])
        ]

    async def stream_ticks(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketTick]:
        approval_key = await self.approval_key()
        async with websockets.connect(self.ws_url, ping_interval=None) as socket:
            for symbol in symbols:
                await socket.send(
                    json.dumps(
                        {
                            "header": {
                                "approval_key": approval_key,
                                "custtype": "P",
                                "tr_type": "1",
                                "content-type": "utf-8",
                            },
                            "body": {"input": {"tr_id": "H0STCNT0", "tr_key": symbol}},
                        }
                    )
                )
            async for message in socket:
                if isinstance(message, bytes):
                    message = message.decode("utf-8")
                if message.startswith("{"):
                    payload = json.loads(message)
                    if payload.get("header", {}).get("tr_id") == "PINGPONG":
                        await socket.send(message)
                    continue
                for tick in parse_trade_message(message):
                    yield tick

    async def _post_json(self, path: str, payload: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.rest_url}{path}", json=payload)
        response.raise_for_status()
        return response.json()

    async def _get_json(
        self, path: str, *, tr_id: str, params: dict[str, str]
    ) -> dict[str, Any]:
        token = await self.access_token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
            "custtype": "P",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.rest_url}{path}", headers=headers, params=params
            )
        response.raise_for_status()
        body = response.json()
        if str(body.get("rt_cd", "0")) != "0":
            raise RuntimeError(str(body.get("msg1") or "KIS request failed"))
        return body


def parse_trade_message(message: str) -> list[MarketTick]:
    parts = message.split("|", 3)
    if len(parts) != 4 or parts[1] != "H0STCNT0":
        return []
    try:
        count = int(parts[2])
    except ValueError:
        return []
    values = parts[3].split("^")
    ticks: list[MarketTick] = []
    width = len(TRADE_COLUMNS)
    for index in range(count):
        row = values[index * width : (index + 1) * width]
        if len(row) < width:
            continue
        data = dict(zip(TRADE_COLUMNS, row))
        try:
            occurred_at = _parse_kis_datetime(data["business_date"], data["trade_time"])
            ticks.append(
                MarketTick(
                    symbol=data["symbol"],
                    occurred_at=occurred_at,
                    price=float(data["price"]),
                    trade_volume=float(data["trade_volume"]),
                    cumulative_volume=float(data["cumulative_volume"]),
                    raw=data,
                )
            )
        except (KeyError, ValueError):
            continue
    return ticks


def _parse_kis_date(value: str) -> datetime:
    date = datetime.strptime(value, "%Y%m%d").date()
    return datetime.combine(date, time.min, tzinfo=SEOUL).astimezone(timezone.utc)


def _parse_kis_datetime(date_value: str, time_value: str) -> datetime:
    value = datetime.strptime(date_value + time_value[:6], "%Y%m%d%H%M%S")
    return value.replace(tzinfo=SEOUL).astimezone(timezone.utc)
