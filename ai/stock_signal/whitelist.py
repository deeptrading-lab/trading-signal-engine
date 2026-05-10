from __future__ import annotations

from .models import AssetType, RiskTier, WhitelistEntry


WHITELIST: tuple[WhitelistEntry, ...] = (
    WhitelistEntry(
        ticker="AAPL",
        name="Apple Inc.",
        asset_type=AssetType.US_EQUITY,
        exchange="NASDAQ",
        currency="USD",
        sector="Technology",
        enabled=True,
        risk_tier=RiskTier.MEDIUM,
        aliases=("APPLE",),
    ),
    WhitelistEntry(
        ticker="BTC-USD",
        name="Bitcoin",
        asset_type=AssetType.CRYPTO,
        exchange="CRYPTO",
        currency="USD",
        sector="Digital Assets",
        enabled=True,
        risk_tier=RiskTier.SPECULATIVE,
        aliases=("BTC", "BITCOIN", "XBT"),
    ),
)


class WhitelistError(ValueError):
    pass


def normalize_ticker(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "BTC":
        return "BTC-USD"
    return normalized


def get_whitelist_entry(value: str) -> WhitelistEntry:
    normalized = normalize_ticker(value)
    for entry in WHITELIST:
        candidates = {entry.ticker, *entry.aliases}
        if normalized in candidates:
            if not entry.enabled:
                raise WhitelistError(f"{entry.ticker}는 현재 분석이 비활성화되어 있습니다")
            return entry
    raise WhitelistError(f"{value.strip().upper()}는 분석 가능한 화이트리스트에 없습니다")
