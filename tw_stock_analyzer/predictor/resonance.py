"""多頭共振六項條件檢查。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tw_stock_analyzer.indicators.fibonacci import (
    FIB_SIGNAL_LOOKBACK,
    FIB_TOLERANCE_PCT,
    FibonacciRetracement,
    compute_fibonacci_retracement,
    is_near_fib_level,
)


@dataclass(frozen=True)
class ResonanceItem:
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class BullishResonance:
    items: tuple[ResonanceItem, ...]
    passed_count: int
    total: int

    @property
    def all_passed(self) -> bool:
        return self.passed_count == self.total


def _bb_width(row: pd.Series) -> float:
    middle = float(row["bb_middle"])
    if middle == 0:
        return 0.0
    return (float(row["bb_upper"]) - float(row["bb_lower"])) / middle


def compute_bullish_resonance(
    df: pd.DataFrame,
    fib: FibonacciRetracement | None = None,
    *,
    volume_ratio_min: float = 1.2,
) -> BullishResonance:
    """檢查六項多頭共振條件（以最新交易日為準）。"""
    if len(df) < 2:
        empty = (ResonanceItem("資料不足", False, "至少需要 2 日資料"),)
        return BullishResonance(items=empty, passed_count=0, total=6)

    latest = df.iloc[-1]
    prev = df.iloc[-2]
    close = float(latest["close"])

    if fib is None:
        fib = compute_fibonacci_retracement(df, lookback=FIB_SIGNAL_LOOKBACK)

    vol_ratio = float(latest.get("volume_ratio_5d", 1.0))
    vol_ok = vol_ratio >= volume_ratio_min
    vol_detail = f"量比 {vol_ratio:.2f}" + ("（放量確認）" if vol_ok else f"（需 ≥ {volume_ratio_min}）")

    sma50 = float(latest["sma_50"])
    sma200 = float(latest["sma_200"])
    sma50_prev = float(prev["sma_50"])
    ma_ok = close > sma50 > sma200 and sma50 > sma50_prev
    ma_detail = (
        f"收 {close:,.0f} > SMA50 {sma50:,.0f} > SMA200 {sma200:,.0f}，SMA50 向上"
        if ma_ok
        else f"收 {close:,.0f} · SMA50 {sma50:,.0f} · SMA200 {sma200:,.0f}"
    )

    width_now = _bb_width(latest)
    width_prev = _bb_width(prev)
    bb_ok = width_now > width_prev
    bb_detail = (
        f"帶寬 {width_now:.3f} > 前日 {width_prev:.3f}（開口）"
        if bb_ok
        else f"帶寬 {width_now:.3f} ≤ 前日 {width_prev:.3f}"
    )

    fib_ok = (
        fib is not None
        and fib.trend == "上升"
        and is_near_fib_level(close, fib, "38.2%", tolerance_pct=FIB_TOLERANCE_PCT)
    )
    if fib_ok:
        level_382 = next(l.price for l in fib.levels if l.label == "38.2%")
        fib_detail = f"收 {close:,.0f} 踩在 38.2% 支撐 {level_382:,.0f}"
    elif fib is None:
        fib_detail = "無法計算 Fib 波段"
    elif fib.trend != "上升":
        fib_detail = f"波段為 {fib.trend}（需上升回撤至 38.2%）"
    else:
        level_382 = next(l.price for l in fib.levels if l.label == "38.2%")
        fib_detail = f"收 {close:,.0f} · 38.2% 支撐 {level_382:,.0f}（需 ±{FIB_TOLERANCE_PCT:.1%} 內）"

    rsi = float(latest["rsi_14"])
    rsi_ok = rsi >= 50
    rsi_detail = (
        f"RSI {rsi:.1f} ≥ 50（守住生命線）"
        if rsi_ok
        else f"RSI {rsi:.1f} < 50（未守住生命線）"
    )

    macd_hist = float(latest["macd_hist"])
    macd = float(latest["macd"])
    macd_signal = float(latest["macd_signal"])
    macd_ok = macd > macd_signal and macd_hist > 0
    macd_detail = (
        f"金叉 · 能量柱 {macd_hist:.4f} > 0（轉正）"
        if macd_ok
        else f"DIF {macd:.4f} · Signal {macd_signal:.4f} · 能量柱 {macd_hist:.4f}"
    )

    items = (
        ResonanceItem("成交量放量確認", vol_ok, vol_detail),
        ResonanceItem("均線多頭排列，方向向上", ma_ok, ma_detail),
        ResonanceItem("布林帶開口", bb_ok, bb_detail),
        ResonanceItem("價格踩在 Fib 38.2% 支撐", fib_ok, fib_detail),
        ResonanceItem("RSI 守住 50 生命線", rsi_ok, rsi_detail),
        ResonanceItem("MACD 金叉，能量柱轉正", macd_ok, macd_detail),
    )
    passed = sum(1 for item in items if item.passed)
    return BullishResonance(items=items, passed_count=passed, total=len(items))
