from __future__ import annotations

from .models import HorizonSummary, PriceBar


HORIZON_WINDOWS: tuple[tuple[str, int], ...] = (
    ("당일", 1),
    ("1W", 5),
    ("1M", 21),
    ("3M", 63),
    ("6M", 126),
    ("1Y", 252),
)


def build_horizon_summaries(bars: list[PriceBar]) -> list[HorizonSummary]:
    if not bars:
        raise ValueError("at least one price bar is required")
    return [_build_horizon(label, bars[-min(window, len(bars)) :]) for label, window in HORIZON_WINDOWS]


def _build_horizon(label: str, bars: list[PriceBar]) -> HorizonSummary:
    start = bars[0]
    end = bars[-1]
    return_pct = _pct(end.close, start.close) or 0.0
    volume_change_pct = _pct(float(end.volume), float(start.volume))
    max_drawdown_pct = _max_drawdown_pct([bar.close for bar in bars])

    if return_pct >= 3.0:
        direction = "BULLISH"
    elif return_pct <= -3.0:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    return HorizonSummary(
        label=label,
        start_date=start.date,
        end_date=end.date,
        start_price=start.close,
        end_price=end.close,
        high=max(bar.high for bar in bars),
        low=min(bar.low for bar in bars),
        return_pct=round(return_pct, 2),
        max_drawdown_pct=round(max_drawdown_pct, 2),
        volume_change_pct=round(volume_change_pct, 2) if volume_change_pct is not None else None,
        direction=direction,
    )


def _pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current / previous - 1.0) * 100.0


def _max_drawdown_pct(values: list[float]) -> float:
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, (value / peak - 1.0) * 100.0)
    return worst
