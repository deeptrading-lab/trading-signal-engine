from __future__ import annotations

import math
import statistics

from .models import PriceBar, TechnicalSnapshot


def _safe_pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current / previous - 1.0) * 100.0


def simple_moving_average(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def relative_strength_index(values: list[float], window: int = 14) -> float | None:
    if len(values) <= window:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for previous, current in zip(values[-window - 1 : -1], values[-window:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(abs(min(change, 0.0)))

    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def annualized_volatility(values: list[float], window: int = 20) -> float | None:
    if len(values) <= window:
        return None

    returns = []
    for previous, current in zip(values[-window - 1 : -1], values[-window:]):
        if previous > 0:
            returns.append(math.log(current / previous))

    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(252) * 100.0


def average_true_range(bars: list[PriceBar], window: int = 14) -> float | None:
    if len(bars) <= window:
        return None

    true_ranges: list[float] = []
    for previous, current in zip(bars[-window - 1 : -1], bars[-window:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )
    return sum(true_ranges) / window


def build_technical_snapshot(bars: list[PriceBar]) -> TechnicalSnapshot:
    if not bars:
        raise ValueError("at least one price bar is required")

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    last = bars[-1]
    avg_volume_20 = simple_moving_average([float(volume) for volume in volumes], 20)
    high_window = bars[-252:] if len(bars) >= 252 else bars

    return TechnicalSnapshot(
        last_price=last.close,
        sma_20=simple_moving_average(closes, 20),
        sma_50=simple_moving_average(closes, 50),
        sma_200=simple_moving_average(closes, 200),
        rsi_14=relative_strength_index(closes, 14),
        return_20d=_safe_pct(closes[-1], closes[-21]) if len(closes) > 20 else None,
        return_60d=_safe_pct(closes[-1], closes[-61]) if len(closes) > 60 else None,
        volatility_20d=annualized_volatility(closes, 20),
        volume_ratio=(last.volume / avg_volume_20) if avg_volume_20 else None,
        high_52w=max(bar.high for bar in high_window),
        low_52w=min(bar.low for bar in high_window),
        atr_14=average_true_range(bars, 14),
    )
