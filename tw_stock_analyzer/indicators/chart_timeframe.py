"""圖表 K 線週期重採樣與指標（僅供圖表顯示，不影響分析引擎）。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from tw_stock_analyzer.indicators.ta_pure import (
    BollingerBands,
    MACD,
    RSIIndicator,
    SMAIndicator,
)

OHLCV_COLS = ("open", "high", "low", "close", "volume")
TW_SHARES_PER_LOT = 1000


def chart_volume_lots(volume: pd.Series) -> pd.Series:
    """台股圖表成交量：內部為股數，轉為張（1 張 = 1000 股，無條件捨去）。"""
    return (volume // TW_SHARES_PER_LOT).astype("int64")


@dataclass(frozen=True)
class ChartTimeframeSpec:
    label: str
    resample_rule: str | None
    sma_fast: int
    sma_slow: int
    fib_unit: str


TIMEFRAME_SPECS: dict[str, ChartTimeframeSpec] = {
    "日線": ChartTimeframeSpec("日線", None, 50, 200, "日"),
    "週線": ChartTimeframeSpec("週線", "W-FRI", 20, 60, "週"),
    "月線": ChartTimeframeSpec("月線", "ME", 6, 12, "月"),
}

CHART_TIMEFRAME_OPTIONS = tuple(TIMEFRAME_SPECS.keys())
CHART_TIMEFRAME_DEFAULT = "日線"

DISPLAY_RANGES_BY_TIMEFRAME: dict[str, tuple[str, ...]] = {
    "日線": ("3 個月", "6 個月", "12 個月"),
    "週線": ("1 年", "3 年", "5 年"),
    "月線": ("2 年", "5 年", "10 年"),
}

DISPLAY_RANGE_FETCH_PERIOD: dict[str, str] = {
    "3 個月": "6mo",
    "6 個月": "1y",
    "12 個月": "2y",
    "1 年": "2y",
    "2 年": "2y",
    "3 年": "5y",
    "5 年": "5y",
    "10 年": "10y",
}

DISPLAY_RANGE_OFFSET: dict[str, pd.DateOffset] = {
    "3 個月": pd.DateOffset(months=3),
    "6 個月": pd.DateOffset(months=6),
    "12 個月": pd.DateOffset(months=12),
    "1 年": pd.DateOffset(years=1),
    "3 年": pd.DateOffset(years=3),
    "5 年": pd.DateOffset(years=5),
    "2 年": pd.DateOffset(years=2),
    "10 年": pd.DateOffset(years=10),
}


def display_range_options_for(timeframe: str) -> tuple[str, ...]:
    """依 K 線週期回傳對應顯示範圍選項。"""
    return DISPLAY_RANGES_BY_TIMEFRAME[timeframe]


def fetch_period_for_display_range(range_label: str) -> str:
    """將顯示範圍標籤轉為 Yahoo Finance 擷取期間。"""
    return DISPLAY_RANGE_FETCH_PERIOD.get(range_label, "2y")


def slice_chart_display_range(df: pd.DataFrame, range_label: str) -> pd.DataFrame:
    """依標籤裁切圖表顯示區間（指標應在完整資料上先算好再呼叫）。"""
    offset = DISPLAY_RANGE_OFFSET.get(range_label)
    if offset is None or df.empty:
        return df

    end = pd.Timestamp(df.index.max())
    if end.tz is not None:
        end = end.tz_localize(None)
    start = end - offset
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    mask = idx >= start
    sliced = df.loc[mask]
    return sliced if not sliced.empty else df


def fib_lookback_bars(timeframe: str, fib_lookback_days: int) -> int:
    """將日線 Fib 波段天數換算為對應週期 K 棒數。"""
    if timeframe == "週線":
        return max(8, round(fib_lookback_days / 5))
    if timeframe == "月線":
        return max(3, round(fib_lookback_days / 21))
    return fib_lookback_days


def fib_calc_dataframe(
    chart_df: pd.DataFrame,
    display_df: pd.DataFrame,
    lookback: int,
) -> pd.DataFrame:
    """取顯示區間結束點往前 lookback 根 K 棒，供斐波那契計算（可超出顯示裁切）。"""
    if display_df.empty:
        return display_df
    end = display_df.index.max()
    hist = chart_df.loc[chart_df.index <= end]
    if hist.empty:
        return display_df
    return hist.tail(lookback) if len(hist) >= lookback else hist


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    ohlcv = df[list(OHLCV_COLS)].copy()
    ohlcv.index = pd.to_datetime(ohlcv.index)
    resampled = (
        ohlcv.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["close"])
    )
    return resampled


def compute_chart_indicators(df: pd.DataFrame, spec: ChartTimeframeSpec) -> pd.DataFrame:
    """在 OHLCV 上計算圖表用指標（保留 NaN 前段以繪製部分均線）。"""
    result = df.copy()
    close = result["close"]
    n = len(result)

    sma_fast = min(spec.sma_fast, max(n - 1, 2))
    sma_slow = min(spec.sma_slow, max(n - 1, 2))
    bb_window = min(20, max(n // 2, 5))

    result["sma_50"] = SMAIndicator(close, window=sma_fast).sma_indicator()
    result["sma_200"] = SMAIndicator(close, window=sma_slow).sma_indicator()
    result["rsi_14"] = RSIIndicator(close, window=min(14, max(n - 1, 2))).rsi()

    macd = MACD(close)
    result["macd"] = macd.macd()
    result["macd_signal"] = macd.macd_signal()
    result["macd_hist"] = macd.macd_diff()

    bb = BollingerBands(close, window=bb_window, window_dev=2)
    result["bb_upper"] = bb.bollinger_hband()
    result["bb_middle"] = bb.bollinger_mavg()
    result["bb_lower"] = bb.bollinger_lband()

    return result


def prepare_chart_data(daily_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """由日線資料產生指定週期圖表 DataFrame（日/週/月）。"""
    spec = TIMEFRAME_SPECS[timeframe]
    if spec.resample_rule is None:
        return compute_chart_indicators(daily_df, spec)
    base = resample_ohlcv(daily_df, spec.resample_rule)
    if base.empty:
        raise ValueError(f"{timeframe} 資料不足，請延長歷史資料期間。")
    return compute_chart_indicators(base, spec)


def format_chart_index(ts: pd.Timestamp, spec: ChartTimeframeSpec) -> str:
    """格式化圖表索引供 UI 顯示。"""
    t = pd.Timestamp(ts)
    if t.tz is not None:
        t = t.tz_convert("Asia/Taipei")
    return t.strftime("%Y-%m-%d")


def hover_key(ts: pd.Timestamp) -> str:
    """產生 hover 對應鍵（毫秒時間戳，與 Plotly x 軸對齊）。"""
    return str(int(pd.Timestamp(ts).value // 1_000_000))


ORDINAL_X_TIMEFRAMES = frozenset(TIMEFRAME_SPECS.keys())


def uses_ordinal_x_axis(spec: ChartTimeframeSpec) -> bool:
    """日/週/月線使用序數 X 軸，避免盤後與假日在時間軸產生視覺空洞。"""
    return spec.label in ORDINAL_X_TIMEFRAMES


def chart_hover_key(bar_index: int, ts: pd.Timestamp, spec: ChartTimeframeSpec) -> str:
    """產生與 Plotly 序數 X 軸對齊的 hover 鍵。"""
    if uses_ordinal_x_axis(spec):
        return str(bar_index)
    return hover_key(ts)
