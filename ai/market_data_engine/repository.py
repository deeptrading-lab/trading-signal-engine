from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from .models import MarketCandle, MarketTick


class RepositoryError(RuntimeError):
    pass


class MarketDataRepository(Protocol):
    async def list_rows(
        self,
        table: str,
        *,
        filters: dict[str, str] | None = None,
        limit: int = 100,
        order: str | None = None,
    ) -> list[dict[str, Any]]: ...

    async def get_row(self, table: str, key: str, value: str) -> dict[str, Any] | None: ...

    async def create_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...

    async def update_row(
        self, table: str, key: str, value: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None: ...

    async def delete_row(self, table: str, key: str, value: str) -> bool: ...

    async def insert_ticks(self, ticks: list[MarketTick]) -> None: ...

    async def upsert_candles(self, candles: list[MarketCandle]) -> None: ...


class SupabaseRepository:
    ALLOWED_TABLES = {
        "instruments",
        "external_analyses",
        "market_ticks",
        "market_candles",
    }

    def __init__(self, url: str, secret_key: str, *, timeout: float = 15.0) -> None:
        self.url = url.rstrip("/")
        self.secret_key = secret_key
        self.timeout = timeout

    async def list_rows(
        self,
        table: str,
        *,
        filters: dict[str, str] | None = None,
        limit: int = 100,
        order: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": "*", "limit": str(min(max(limit, 1), 1000))}
        if order:
            params["order"] = order
        for key, value in (filters or {}).items():
            params[key] = f"eq.{value}"
        result = await self._request(table, params=params)
        return list(result)

    async def get_row(self, table: str, key: str, value: str) -> dict[str, Any] | None:
        result = await self._request(
            table, params={"select": "*", key: f"eq.{value}", "limit": "1"}
        )
        return result[0] if result else None

    async def create_row(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        result = await self._request(
            table,
            method="POST",
            payload=[_jsonable(row)],
            prefer="return=representation",
        )
        return result[0]

    async def update_row(
        self, table: str, key: str, value: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        if not changes:
            return await self.get_row(table, key, value)
        result = await self._request(
            table,
            method="PATCH",
            params={key: f"eq.{value}"},
            payload=_jsonable(changes),
            prefer="return=representation",
        )
        return result[0] if result else None

    async def delete_row(self, table: str, key: str, value: str) -> bool:
        result = await self._request(
            table,
            method="DELETE",
            params={key: f"eq.{value}"},
            prefer="return=representation",
        )
        return bool(result)

    async def insert_ticks(self, ticks: list[MarketTick]) -> None:
        if not ticks:
            return
        await self._request(
            "market_ticks",
            method="POST",
            payload=[_jsonable(tick.model_dump()) for tick in ticks],
            prefer="return=minimal",
        )

    async def upsert_candles(self, candles: list[MarketCandle]) -> None:
        if not candles:
            return
        await self._request(
            "market_candles",
            method="POST",
            params={"on_conflict": "symbol,interval,opened_at"},
            payload=[_jsonable(item.model_dump()) for item in candles],
            prefer="resolution=merge-duplicates,return=minimal",
        )

    async def _request(
        self,
        table: str,
        *,
        method: str = "GET",
        params: dict[str, str] | None = None,
        payload: object | None = None,
        prefer: str = "",
    ) -> Any:
        if table not in self.ALLOWED_TABLES:
            raise ValueError(f"unsupported table: {table}")
        headers = {
            "apikey": self.secret_key,
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.url}/rest/v1/{quote(table)}",
                    headers=headers,
                    params=params,
                    json=payload,
                )
            response.raise_for_status()
            return response.json() if response.content else []
        except (httpx.HTTPError, ValueError) as error:
            raise RepositoryError(f"Supabase request failed: {error}") from error


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
