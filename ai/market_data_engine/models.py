from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InstrumentCreate(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    name: str = Field(min_length=1, max_length=100)
    market: str = Field(default="KRX", min_length=1, max_length=20)
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class InstrumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    market: str | None = Field(default=None, min_length=1, max_length=20)
    enabled: bool | None = None


class ExternalAnalysisCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    analysis_type: str = Field(min_length=1, max_length=80)
    source: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any]
    observed_at: datetime = Field(default_factory=utc_now)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class ExternalAnalysisUpdate(BaseModel):
    analysis_type: str | None = Field(default=None, min_length=1, max_length=80)
    source: str | None = Field(default=None, min_length=1, max_length=120)
    payload: dict[str, Any] | None = None
    observed_at: datetime | None = None


class MarketTick(BaseModel):
    symbol: str
    occurred_at: datetime
    price: float
    trade_volume: float
    cumulative_volume: float | None = None
    source: str = "kis"
    raw: dict[str, Any] = Field(default_factory=dict)


class MarketCandle(BaseModel):
    symbol: str
    interval: Literal["1m", "1d", "1w", "1mo"]
    opened_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "kis"


class CandleSyncRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=12)
    interval: Literal["1m", "1d", "1w", "1mo"]
    start: str | None = None
    end: str | None = None
    hour: str | None = None
