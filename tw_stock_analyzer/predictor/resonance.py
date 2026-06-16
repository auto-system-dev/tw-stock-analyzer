"""多頭共振六項條件檢查。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from tw_stock_analyzer.indicators.fibonacci import (
    FIB_SIGNAL_LOOKBACK,
    FIB_TOLERANCE_PCT,
    FibonacciRetracement,
    compute_fibonacci_retracement,
    evaluate_fib382_reaction,
    evaluate_fib618_reaction,
    format_fib382_reaction_detail,
    format_fib618_reaction_detail,
    get_fib_level_price,
)

BB_MIDDLE_RISE_DAYS = 3
BB_BREAKOUT_LOOKBACK = 20
BB_UPPER_TOLERANCE_PCT = 0.005
MACD_CROSS_LOOKBACK = 5
MACD_HIST_EXPAND_DAYS = 2


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


def _bb_breakout_retest_hold(
    df: pd.DataFrame,
    *,
    lookback: int = BB_BREAKOUT_LOOKBACK,
    tolerance_pct: float = BB_UPPER_TOLERANCE_PCT,
) -> tuple[bool, str]:
    """突破上軌後回踩上軌不破，且最新交易日收盤站穩上軌上方。"""
    if len(df) < 4:
        return False, "資料不足"

    latest = df.iloc[-1]
    window = df.iloc[-lookback:] if len(df) >= lookback else df
    if len(window) < 3:
        return False, "資料不足"

    breakout_pos: int | None = None
    for i in range(len(window) - 2):
        row = window.iloc[i]
        if float(row["close"]) > float(row["bb_upper"]):
            breakout_pos = i

    if breakout_pos is None:
        return False, "近期無突破上軌"

    segment = window.iloc[breakout_pos + 1 :]
    retest_found = False
    for i in range(len(segment)):
        row = segment.iloc[i]
        upper = float(row["bb_upper"])
        low = float(row["low"])
        if upper <= 0:
            continue
        held_floor = upper * (1 - tolerance_pct)
        near_upper = low <= upper * (1 + tolerance_pct)
        if near_upper:
            if low < held_floor:
                return False, f"回踩破上軌（低 {low:,.0f} < 上軌 {upper:,.0f}）"
            retest_found = True

    if not retest_found:
        return False, "突破後尚未回踩上軌"

    today_close = float(latest["close"])
    today_upper = float(latest["bb_upper"])
    if today_upper <= 0:
        return False, "上軌無效"
    if today_close < today_upper * (1 - tolerance_pct):
        return False, f"收 {today_close:,.0f} 未站穩上軌 {today_upper:,.0f}"

    return True, (
        f"突破後回踩站穩（收 {today_close:,.0f} ≥ 上軌 {today_upper:,.0f}）"
    )


def _bb_middle_rising(
    df: pd.DataFrame,
    *,
    days: int = BB_MIDDLE_RISE_DAYS,
) -> tuple[bool, str]:
    """中軌連續 N 日上升。"""
    if len(df) < days:
        return False, f"資料不足（需 {days} 日）"

    tail = df.tail(days)
    middles = tail["bb_middle"].astype(float)
    for i in range(1, len(middles)):
        if middles.iloc[i] <= middles.iloc[i - 1]:
            prev_m = middles.iloc[i - 1]
            cur_m = middles.iloc[i]
            return False, f"中軌未連續上升（{prev_m:,.0f} → {cur_m:,.0f}）"

    first_m = middles.iloc[0]
    last_m = middles.iloc[-1]
    return True, f"中軌連續 {days} 日上升（{first_m:,.0f} → {last_m:,.0f}）"


def _macd_golden_cross_in_lookback(
    df: pd.DataFrame,
    *,
    lookback: int = MACD_CROSS_LOOKBACK,
) -> tuple[bool, str]:
    """近 N 日內曾出現 DIF 上穿 Signal 的金叉。"""
    if len(df) < 2:
        return False, "資料不足"

    window = df.iloc[-lookback:] if len(df) >= lookback else df
    cross_detail = ""
    for i in range(1, len(window)):
        row = window.iloc[i]
        prev_row = window.iloc[i - 1]
        macd = float(row["macd"])
        macd_signal = float(row["macd_signal"])
        macd_prev = float(prev_row["macd"])
        macd_signal_prev = float(prev_row["macd_signal"])
        if macd_prev <= macd_signal_prev and macd > macd_signal:
            cross_detail = (
                f"近 {lookback} 日內金叉 · DIF {macd:.4f} 上穿 Signal {macd_signal:.4f}"
            )

    if cross_detail:
        return True, cross_detail
    return False, f"近 {lookback} 日無金叉"


def _macd_hist_expanding(
    df: pd.DataFrame,
    *,
    days: int = MACD_HIST_EXPAND_DAYS,
) -> tuple[bool, str]:
    """能量柱連續 N 日放大（逐日遞增）。"""
    need = days + 1
    if len(df) < need:
        return False, f"資料不足（需 {need} 日）"

    hist = df.tail(need)["macd_hist"].astype(float)
    for i in range(1, len(hist)):
        if hist.iloc[i] <= hist.iloc[i - 1]:
            prev_h = hist.iloc[i - 1]
            cur_h = hist.iloc[i]
            return False, f"能量柱未連續放大（{prev_h:.4f} → {cur_h:.4f}）"

    first_h = hist.iloc[0]
    last_h = hist.iloc[-1]
    return True, f"能量柱連續 {days} 日放大（{first_h:.4f} → {last_h:.4f}）"


def _macd_above_zero_bullish(latest: pd.Series) -> tuple[bool, str]:
    """DIF、Signal 均在 0 軸上方，且 DIF > Signal。"""
    macd = float(latest["macd"])
    macd_signal = float(latest["macd_signal"])
    ok = macd > 0 and macd_signal > 0 and macd > macd_signal
    if ok:
        return (
            True,
            f"0 軸上方多頭（DIF {macd:.4f} > Signal {macd_signal:.4f} > 0）",
        )

    parts: list[str] = []
    if macd <= 0:
        parts.append(f"DIF {macd:.4f} ≤ 0")
    if macd_signal <= 0:
        parts.append(f"Signal {macd_signal:.4f} ≤ 0")
    if macd <= macd_signal:
        parts.append(f"DIF {macd:.4f} ≤ Signal {macd_signal:.4f}")
    return False, " · ".join(parts)


def compute_bullish_resonance(
    df: pd.DataFrame,
    fib: FibonacciRetracement | None = None,
    *,
    volume_ratio_min: float = 1.2,
    bb_middle_rise_days: int = BB_MIDDLE_RISE_DAYS,
    bb_breakout_lookback: int = BB_BREAKOUT_LOOKBACK,
    bb_upper_tolerance_pct: float = BB_UPPER_TOLERANCE_PCT,
    macd_cross_lookback: int = MACD_CROSS_LOOKBACK,
    macd_hist_expand_days: int = MACD_HIST_EXPAND_DAYS,
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
    width_ok = width_now > width_prev
    hold_ok, hold_detail = _bb_breakout_retest_hold(
        df,
        lookback=bb_breakout_lookback,
        tolerance_pct=bb_upper_tolerance_pct,
    )
    middle_ok, middle_detail = _bb_middle_rising(df, days=bb_middle_rise_days)
    bb_ok = width_ok and hold_ok and middle_ok
    width_detail = (
        f"帶寬 {width_now:.3f} > 前日 {width_prev:.3f}（開口）"
        if width_ok
        else f"帶寬 {width_now:.3f} ≤ 前日 {width_prev:.3f}"
    )
    bb_detail = f"{width_detail} · {hold_detail} · {middle_detail}"

    fib_ok = False
    fib_detail = ""
    if fib is None:
        fib_detail = "無法計算 Fib 波段"
    elif fib.trend != "上升":
        fib_detail = f"波段為 {fib.trend}（需上升回撤至 Fib 支撐）"
    else:
        reaction_382 = evaluate_fib382_reaction(
            df,
            latest,
            prev,
            fib,
            tolerance_pct=FIB_TOLERANCE_PCT,
            volume_ratio_min=volume_ratio_min,
        )
        reaction_618 = evaluate_fib618_reaction(
            latest,
            prev,
            fib,
            tolerance_pct=FIB_TOLERANCE_PCT,
            volume_ratio_min=volume_ratio_min,
        )
        level_382 = get_fib_level_price(fib, "38.2%")
        level_618 = get_fib_level_price(fib, "61.8%")
        level_786 = get_fib_level_price(fib, "78.6%")

        if reaction_382.passes:
            fib_ok = True
            fib_detail = format_fib382_reaction_detail(
                reaction_382,
                level_382=level_382,
                close=close,
            )
        elif reaction_618.passes:
            fib_ok = True
            fib_detail = format_fib618_reaction_detail(
                reaction_618,
                level_618=level_618,
                level_786=level_786,
                close=close,
            )
        elif reaction_382.at_zone:
            fib_detail = format_fib382_reaction_detail(
                reaction_382,
                level_382=level_382,
                close=close,
            )
        elif reaction_618.at_zone:
            fib_detail = format_fib618_reaction_detail(
                reaction_618,
                level_618=level_618,
                level_786=level_786,
                close=close,
            )
        else:
            fib_detail = (
                f"收 {close:,.0f} · 38.2% 支撐 {level_382:,.0f} · "
                f"61.8% 支撐 {level_618:,.0f} · "
                f"78.6% 止損 {level_786:,.0f}（需 ±{FIB_TOLERANCE_PCT:.1%} 內；"
                f"38.2% 需強勢趨勢+缩量+K線反轉+放量；"
                f"61.8% 需長下影/吞沒/放量至少 2 項且未破 78.6%）"
            )

    rsi = float(latest["rsi_14"])
    rsi_ok = rsi >= 50
    rsi_detail = (
        f"RSI {rsi:.1f} ≥ 50（守住生命線）"
        if rsi_ok
        else f"RSI {rsi:.1f} < 50（未守住生命線）"
    )

    cross_ok, cross_detail = _macd_golden_cross_in_lookback(
        df, lookback=macd_cross_lookback
    )
    zero_ok, zero_detail = _macd_above_zero_bullish(latest)
    expand_ok, expand_detail = _macd_hist_expanding(df, days=macd_hist_expand_days)
    macd_ok = cross_ok and zero_ok and expand_ok
    macd_detail = f"{cross_detail} · {zero_detail} · {expand_detail}"

    items = (
        ResonanceItem("成交量放量確認", vol_ok, vol_detail),
        ResonanceItem("均線多頭排列，方向向上", ma_ok, ma_detail),
        ResonanceItem("布林帶開口", bb_ok, bb_detail),
        ResonanceItem("Fib 支撐（38.2% 或 61.8% 真反应）", fib_ok, fib_detail),
        ResonanceItem("RSI 守住 50 生命線", rsi_ok, rsi_detail),
        ResonanceItem("MACD 金叉、0 軸多頭、能量柱放大", macd_ok, macd_detail),
    )
    passed = sum(1 for item in items if item.passed)
    return BullishResonance(items=items, passed_count=passed, total=len(items))
