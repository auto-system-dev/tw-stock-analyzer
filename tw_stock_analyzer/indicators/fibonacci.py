"""斐波那契回撤與擴展計算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

import pandas as pd

FIB_SIGNAL_LOOKBACK = 60
FIB_TOLERANCE_PCT = 0.015

FIB_LOOKBACK_TIERS: dict[int, str] = {
    13: "短期",
    21: "短期",
    34: "中期",
    55: "中期",
    89: "長期",
    144: "長期",
}
FIB_LOOKBACK_OPTIONS: tuple[int, ...] = tuple(FIB_LOOKBACK_TIERS.keys())
FIB_LOOKBACK_DEFAULT = 55


def format_fib_lookback_label(days: int) -> str:
    """儀表板斐波那契波段天數選項顯示文字。"""
    tier = FIB_LOOKBACK_TIERS.get(days)
    if tier:
        return f"{days} 日（{tier}）"
    return f"{days} 日"

FIB_RATIOS: tuple[tuple[float, str], ...] = (
    (0.0, "0%"),
    (0.236, "23.6%"),
    (0.382, "38.2%"),
    (0.5, "50%"),
    (0.618, "61.8%"),
    (0.786, "78.6%"),
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


@dataclass(frozen=True)
class Fib382Reaction:
    """38.2% 支撐區的進場確認（強勢趨勢 + 缩量回調 + K 線反轉 + 放量上攻）。"""

    at_zone: bool
    strong_trend: bool
    pullback_shrink: bool
    reversal: bool
    bounce_volume: bool

    @property
    def passes(self) -> bool:
        return (
            self.at_zone
            and self.strong_trend
            and self.pullback_shrink
            and self.reversal
            and self.bounce_volume
        )


@dataclass(frozen=True)
class Fib618Reaction:
    """61.8% 支撐區的真反应跡象（對應常見斐波那契進場確認）。"""

    at_zone: bool
    above_stop: bool
    pin_bar: bool
    engulfing: bool
    volume_spike: bool

    @property
    def reaction_score(self) -> int:
        return int(self.pin_bar) + int(self.engulfing) + int(self.volume_spike)

    @property
    def passes(self) -> bool:
        return self.at_zone and self.above_stop and self.reaction_score >= 2


def get_fib_level_price(fib: FibonacciRetracement, label: str) -> float:
    return _level_price(fib, label)


def _touches_fib_zone(
    row: pd.Series,
    level: float,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
) -> bool:
    """收盤或低點是否落在 Fib 價位附近。"""
    close = float(row["close"])
    low = float(row["low"])
    return _is_near(close, level, tolerance_pct) or _is_near(low, level, tolerance_pct)


def is_pin_bar_at_support(
    row: pd.Series,
    support_level: float,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
) -> bool:
    """長下影線（Pin Bar）：低點探及支撐、下影線顯著長於實體。"""
    o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
    total_range = h - l
    if total_range <= 0:
        return False
    body = abs(c - o)
    lower_shadow = min(o, c) - l
    if not _is_near(l, support_level, tolerance_pct):
        return False
    if lower_shadow < total_range * 0.5:
        return False
    if body > 0 and lower_shadow < body * 1.5:
        return False
    return lower_shadow >= body or body == 0


def is_bullish_engulfing(prev: pd.Series, latest: pd.Series) -> bool:
    """看漲吞沒：前日陰線、當日陽線且實體完全包住前日。"""
    po, pc = float(prev["open"]), float(prev["close"])
    lo, lc = float(latest["open"]), float(latest["close"])
    if pc >= po or lc <= lo:
        return False
    return lo <= pc and lc >= po


def is_hammer_at_support(
    row: pd.Series,
    support_level: float,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
) -> bool:
    """錘子線：低點探及支撐、下影線長、上影線短、收盤偏上。"""
    o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
    total_range = h - l
    if total_range <= 0:
        return False
    body = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    mid = (h + l) / 2
    if not _is_near(l, support_level, tolerance_pct):
        return False
    if c < mid:
        return False
    if body > 0:
        return lower_shadow >= body * 2 and upper_shadow <= body
    return lower_shadow >= upper_shadow * 2


def is_bullish_reversal_at_support(
    prev: pd.Series,
    latest: pd.Series,
    support_level: float,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
) -> bool:
    """K 線反轉：錘子線或看漲吞沒。"""
    return is_hammer_at_support(
        latest, support_level, tolerance_pct=tolerance_pct
    ) or is_bullish_engulfing(prev, latest)


def _retracement_volume_shrink(
    df: pd.DataFrame,
    fib: FibonacciRetracement,
) -> bool:
    """回調缩量：回撤段均量低於上漲段均量。"""
    if fib.trend != "上升":
        return False
    low_ts = pd.Timestamp(fib.swing_low_date)
    high_ts = pd.Timestamp(fib.swing_high_date)
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    mask_impulse = (idx >= low_ts) & (idx <= high_ts)
    mask_retrace = idx > high_ts
    impulse = df.loc[mask_impulse]
    retracement = df.loc[mask_retrace]
    if len(impulse) < 2 or len(retracement) < 2:
        return False
    impulse_avg = float(impulse["volume"].mean())
    retrace_avg = float(retracement.iloc[:-1]["volume"].mean())
    if impulse_avg <= 0:
        return False
    return retrace_avg < impulse_avg


def _has_strong_uptrend(latest: pd.Series, fib: FibonacciRetracement) -> bool:
    """強勢趨勢：均線多頭排列，或仍處於波段高點區間。"""
    close = float(latest["close"])
    sma50 = float(latest.get("sma_50", 0))
    sma200 = float(latest.get("sma_200", 0))
    ma_bull = sma50 > 0 and sma200 > 0 and close > sma50 > sma200
    in_upper_range = close >= fib.swing_low + (fib.swing_high - fib.swing_low) * 0.5
    return ma_bull or in_upper_range


def evaluate_fib382_reaction(
    df: pd.DataFrame,
    latest: pd.Series,
    prev: pd.Series,
    fib: FibonacciRetracement,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
    volume_ratio_min: float = 1.2,
) -> Fib382Reaction:
    """評估 38.2% 附近是否具備圖示進場確認信號。"""
    level_382 = get_fib_level_price(fib, "38.2%")
    at_zone = _touches_fib_zone(latest, level_382, tolerance_pct=tolerance_pct)
    strong_trend = _has_strong_uptrend(latest, fib)
    pullback_shrink = _retracement_volume_shrink(df, fib)
    reversal = is_bullish_reversal_at_support(
        prev, latest, level_382, tolerance_pct=tolerance_pct
    )
    vol_ratio = float(latest.get("volume_ratio_5d", 1.0))
    prev_vol = float(prev.get("volume", 0))
    latest_vol = float(latest.get("volume", 0))
    bounce_volume = vol_ratio >= volume_ratio_min or (
        prev_vol > 0 and latest_vol >= prev_vol * 1.2
    )
    return Fib382Reaction(
        at_zone=at_zone,
        strong_trend=strong_trend,
        pullback_shrink=pullback_shrink,
        reversal=reversal,
        bounce_volume=bounce_volume,
    )


def format_fib382_reaction_detail(
    reaction: Fib382Reaction,
    *,
    level_382: float,
    close: float,
) -> str:
    """格式化 38.2% 進場確認說明。"""
    mark = lambda ok: "✓" if ok else "✗"
    parts = [
        f"38.2% 支撐 {level_382:,.0f}",
        f"強勢趨勢 {mark(reaction.strong_trend)}",
        f"回調缩量 {mark(reaction.pullback_shrink)}",
        f"K線反轉 {mark(reaction.reversal)}",
        f"放量上攻 {mark(reaction.bounce_volume)}",
    ]
    if reaction.passes:
        return f"收 {close:,.0f} · " + " · ".join(parts) + "（38.2% 確認）"
    if not reaction.at_zone:
        return f"收 {close:,.0f} · 未在 38.2% ±{FIB_TOLERANCE_PCT:.1%} 區"
    return f"收 {close:,.0f} · " + " · ".join(parts) + "（需全項確認）"


def evaluate_fib618_reaction(
    latest: pd.Series,
    prev: pd.Series,
    fib: FibonacciRetracement,
    *,
    tolerance_pct: float = FIB_TOLERANCE_PCT,
    volume_ratio_min: float = 1.2,
) -> Fib618Reaction:
    """評估價格在 61.8% 附近是否出現止跌真反应。"""
    level_618 = get_fib_level_price(fib, "61.8%")
    level_786 = get_fib_level_price(fib, "78.6%")
    close = float(latest["close"])
    at_zone = _touches_fib_zone(latest, level_618, tolerance_pct=tolerance_pct)
    above_stop = close > level_786
    pin_bar = is_pin_bar_at_support(latest, level_618, tolerance_pct=tolerance_pct)
    engulfing = is_bullish_engulfing(prev, latest)
    vol_ratio = float(latest.get("volume_ratio_5d", 1.0))
    prev_vol = float(prev.get("volume", 0))
    latest_vol = float(latest.get("volume", 0))
    volume_spike = vol_ratio >= volume_ratio_min or (
        prev_vol > 0 and latest_vol >= prev_vol * 1.2
    )
    return Fib618Reaction(
        at_zone=at_zone,
        above_stop=above_stop,
        pin_bar=pin_bar,
        engulfing=engulfing,
        volume_spike=volume_spike,
    )


def format_fib618_reaction_detail(
    reaction: Fib618Reaction,
    *,
    level_618: float,
    level_786: float,
    close: float,
) -> str:
    """格式化 61.8% 真反应檢查說明。"""
    mark = lambda ok: "✓" if ok else "✗"
    parts = [
        f"61.8% 支撐 {level_618:,.0f}",
        f"長下影 {mark(reaction.pin_bar)}",
        f"吞沒 {mark(reaction.engulfing)}",
        f"放量 {mark(reaction.volume_spike)}",
        f"未破 78.6% ({level_786:,.0f}) {mark(reaction.above_stop)}",
    ]
    if reaction.passes:
        return f"收 {close:,.0f} · " + " · ".join(parts) + "（真反应確認）"
    if not reaction.at_zone:
        return f"收 {close:,.0f} · 未在 61.8% ±{FIB_TOLERANCE_PCT:.1%} 區"
    return f"收 {close:,.0f} · " + " · ".join(parts) + "（需至少 2 項止跌跡象）"


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
