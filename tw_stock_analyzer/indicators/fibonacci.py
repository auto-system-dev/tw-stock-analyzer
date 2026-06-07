"""斐波那契回撤與擴展計算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import pandas as pd

FIB_SIGNAL_LOOKBACK = 60
FIB_TOLERANCE_PCT = 0.015

FIB_RATIOS: tuple[tuple[float, str], ...] = (
    (0.0, "0%"),
    (0.382, "38.2%"),
    (0.5, "50%"),
    (0.618, "61.8%"),
    (1.0, "100%"),
)

FIB_EXTENSION_RATIOS: tuple[tuple[float, str], ...] = (
    (0.618, "61.8%"),
    (1.0, "100%"),
    (1.272, "127.2%"),
    (1.618, "161.8%"),
    (2.0, "200%"),
    (2.618, "261.8%"),
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


@dataclass(frozen=True)
class FibonacciExtension:
    point_a: float
    point_b: float
    point_c: float
    point_a_date: pd.Timestamp
    point_b_date: pd.Timestamp
    point_c_date: pd.Timestamp
    trend: str
    lookback_days: int
    levels: tuple[FibLevel, ...]


FibOverlay: TypeAlias = FibonacciRetracement | FibonacciExtension


def _bar_index_for_date(df: pd.DataFrame, ts: pd.Timestamp) -> int:
    target = pd.Timestamp(ts)
    for i, idx in enumerate(df.index):
        if pd.Timestamp(idx) == target:
            return i
    loc = df.index.get_loc(target)
    if isinstance(loc, int):
        return loc
    if isinstance(loc, slice):
        return int(loc.start or 0)
    return int(loc[0])


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


def compute_fibonacci_extension(
    df: pd.DataFrame,
    lookback: int = 60,
) -> FibonacciExtension | None:
    """依最近 lookback 根 K 棒的三點波段（A→B→C）計算斐波那契擴展目標價。"""
    if len(df) < lookback:
        return None

    window = df.tail(lookback)
    high_date = window["high"].idxmax()
    low_date = window["low"].idxmin()
    swing_high = float(window.loc[high_date, "high"])
    swing_low = float(window.loc[low_date, "low"])

    if swing_high <= swing_low:
        return None

    low_pos = int(window.index.get_loc(low_date))
    high_pos = int(window.index.get_loc(high_date))

    if low_pos < high_pos:
        trend = "上升"
        point_a = swing_low
        point_b = swing_high
        point_a_date = pd.Timestamp(low_date)
        point_b_date = pd.Timestamp(high_date)
        after_impulse = window.iloc[high_pos + 1 :]
        if after_impulse.empty:
            return None
        c_date = after_impulse["low"].idxmin()
        point_c = float(window.loc[c_date, "low"])
        point_c_date = pd.Timestamp(c_date)
        if point_c >= point_b or point_c <= point_a:
            return None
        impulse = point_b - point_a
        levels = tuple(
            FibLevel(ratio, label, point_c + ratio * impulse)
            for ratio, label in FIB_EXTENSION_RATIOS
        )
    else:
        trend = "下降"
        point_a = swing_high
        point_b = swing_low
        point_a_date = pd.Timestamp(high_date)
        point_b_date = pd.Timestamp(low_date)
        after_impulse = window.iloc[low_pos + 1 :]
        if after_impulse.empty:
            return None
        c_date = after_impulse["high"].idxmax()
        point_c = float(window.loc[c_date, "high"])
        point_c_date = pd.Timestamp(c_date)
        if point_c <= point_b or point_c >= point_a:
            return None
        impulse = point_a - point_b
        levels = tuple(
            FibLevel(ratio, label, point_c - ratio * impulse)
            for ratio, label in FIB_EXTENSION_RATIOS
        )

    return FibonacciExtension(
        point_a=point_a,
        point_b=point_b,
        point_c=point_c,
        point_a_date=point_a_date,
        point_b_date=point_b_date,
        point_c_date=point_c_date,
        trend=trend,
        lookback_days=lookback,
        levels=levels,
    )


def build_fib_anchor_config(
    df: pd.DataFrame,
    fib: FibOverlay,
    x_coords: list,
    *,
    mode: str,
    is_ordinal: bool,
) -> dict:
    """建立前端手動斐波那契所需的錨點與 K 棒資料。"""
    bars: list[dict] = []
    for i, (_, row) in enumerate(df.iterrows()):
        x = x_coords[i]
        if not is_ordinal:
            x = int(pd.Timestamp(df.index[i]).value // 1_000_000)
        bars.append(
            {
                "index": i,
                "x": x,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
        )

    if isinstance(fib, FibonacciRetracement):
        low_i = _bar_index_for_date(df, fib.swing_low_date)
        high_i = _bar_index_for_date(df, fib.swing_high_date)
        anchors = [
            {
                "id": "low",
                "role": "low",
                "barIndex": low_i,
                "price": fib.swing_low,
                "label": "低",
            },
            {
                "id": "high",
                "role": "high",
                "barIndex": high_i,
                "price": fib.swing_high,
                "label": "高",
            },
        ]
    else:
        anchors = [
            {
                "id": "a",
                "role": "a",
                "barIndex": _bar_index_for_date(df, fib.point_a_date),
                "price": fib.point_a,
                "label": "A",
            },
            {
                "id": "b",
                "role": "b",
                "barIndex": _bar_index_for_date(df, fib.point_b_date),
                "price": fib.point_b,
                "label": "B",
            },
            {
                "id": "c",
                "role": "c",
                "barIndex": _bar_index_for_date(df, fib.point_c_date),
                "price": fib.point_c,
                "label": "C",
            },
        ]

    return {
        "enabled": True,
        "mode": mode,
        "anchors": anchors,
        "bars": bars,
    }


def _level_price(fib: FibonacciRetracement, label: str) -> float:
    for level in fib.levels:
        if level.label == label:
            return level.price
    raise ValueError(f"找不到 Fib 比例：{label}")


def _is_near(price: float, level: float, tolerance_pct: float) -> bool:
    if level <= 0:
        return False
    return abs(price - level) / level <= tolerance_pct


def is_near_fib_level(
    price: float,
    fib: FibonacciRetracement | None,
    label: str,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
) -> bool:
    """收盤價是否落在指定 Fib 比例價位附近。"""
    if fib is None:
        return False
    return _is_near(price, _level_price(fib, label), tolerance_pct)


def fibonacci_signal(
    close: float,
    fib: FibonacciRetracement | None,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
) -> str:
    """依收盤價與斐波那契回撤價位判斷支撐／壓力訊號。"""
    if fib is None:
        return "中性"

    key_levels = ("38.2%", "50%", "61.8%")
    near_key = any(
        _is_near(close, _level_price(fib, label), tolerance_pct) for label in key_levels
    )

    if fib.trend == "上升":
        support_618 = _level_price(fib, "61.8%")
        if near_key:
            return "回撤支撐區"
        if close < support_618 * (1 - tolerance_pct):
            return "支撐失守"
        return "中性"

    if near_key:
        return "反彈壓力區"
    return "中性"
