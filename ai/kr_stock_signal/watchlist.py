from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchlistSymbol:
    symbol: str
    name_ko: str
    market: str


WATCHLIST: dict[str, WatchlistSymbol] = {
    "005930.KS": WatchlistSymbol("005930.KS", "삼성전자", "KOSPI"),
    "000660.KS": WatchlistSymbol("000660.KS", "SK하이닉스", "KOSPI"),
    "005380.KS": WatchlistSymbol("005380.KS", "현대차", "KOSPI"),
}

ALIASES: dict[str, str] = {
    "삼성전자": "005930.KS",
    "005930": "005930.KS",
    "005930.KS": "005930.KS",
    "SK하이닉스": "000660.KS",
    "sk하이닉스": "000660.KS",
    "하이닉스": "000660.KS",
    "000660": "000660.KS",
    "000660.KS": "000660.KS",
    "현대차": "005380.KS",
    "현대자동차": "005380.KS",
    "005380": "005380.KS",
    "005380.KS": "005380.KS",
}


def normalize_symbol(value: str) -> str:
    key = value.strip()
    return ALIASES.get(key, key.upper())


def require_watchlist_symbol(value: str) -> WatchlistSymbol:
    symbol = normalize_symbol(value)
    if symbol not in WATCHLIST:
        raise ValueError(f"watchlist 등록 필요: {value}")
    return WATCHLIST[symbol]
