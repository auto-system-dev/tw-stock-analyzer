"""斐波那契回撤計算。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FIB_RATIOS: tuple[tuple[float, str], ...] = (
    (0.0, "0%"),
    (0.382, "38.2%"),
    (0.5, "50%"),
    (0.618, "61.8%"),
    (1.0, "100%"),
)


@dataclass(frozen=True)
class FibLevel:
    ratio: float
    label: str
    price: float


@dataclass(frozen=True)
class FibonacciRetracement:
    swing_high: float
    swing_low: float
    swing_high_date: pd.Timestamp
    swing_low_date: pd.Timestamp
    trend: str
    lookback_days: int
    levels: tuple[FibLevel, ...]


def compute_fibonacci_retracement(
    df: pd.DataFrame,
    lookback: int = 60,
) -> FibonacciRetracement | None:
    """依最近 lookback 根 K 棒的波段高低點計算斐波那契回撤價位。"""
    if len(df) < lookback:
        return None

    window = df.tail(lookback)
    high_date = window["high"].idxmax()
    low_date = window["low"].idxmin()
    swing_high = float(window.loc[high_date, "high"])
    swing_low = float(window.loc[low_date, "low"])

    if swing_high <= swing_low:
        return None

    low_pos = window.index.get_loc(low_date)
    high_pos = window.index.get_loc(high_date)

    if low_pos < high_pos:
        trend = "上升"
        levels = tuple(
            FibLevel(ratio, label, swing_high - ratio * (swing_high - swing_low))
            for ratio, label in FIB_RATIOS
        )
    else:
        trend = "下降"
        levels = tuple(
            FibLevel(ratio, label, swing_low + ratio * (swing_high - swing_low))
            for ratio, label in FIB_RATIOS
        )

    return FibonacciRetracement(
        swing_high=swing_high,
        swing_low=swing_low,
        swing_high_date=pd.Timestamp(high_date),
        swing_low_date=pd.Timestamp(low_date),
        trend=trend,
        lookback_days=lookback,
        levels=levels,
    )
