"""圖表 K 線週期重採樣與指標（僅供圖表顯示，不影響分析引擎）。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

from tw_stock_analyzer.data.fetcher import StockFetcher

OHLCV_COLS = ("open", "high", "low", "close", "volume")

# 台股單日盤中約 270 分鐘（09:00–13:30）
MINUTES_PER_SESSION = 270

INTRADAY_BAR_MINUTES: dict[str, int] = {
    "1分": 1,
    "5分": 5,
    "15分": 15,
    "30分": 30,
    "60分": 60,
}


@dataclass(frozen=True)
class ChartTimeframeSpec:
    label: str
    resample_rule: str | None
    sma_fast: int
    sma_slow: int
    fib_unit: str
    yf_interval: str | None = None
    yf_period: str | None = None

    @property
    def is_intraday(self) -> bool:
        return self.yf_interval is not None


TIMEFRAME_SPECS: dict[str, ChartTimeframeSpec] = {
    "1分": ChartTimeframeSpec("1分", None, 60, 240, "根", "1m", "7d"),
    "5分": ChartTimeframeSpec("5分", None, 60, 240, "根", "5m", "60d"),
    "15分": ChartTimeframeSpec("15分", None, 60, 240, "根", "15m", "60d"),
    "30分": ChartTimeframeSpec("30分", None, 60, 240, "根", "30m", "60d"),
    "60分": ChartTimeframeSpec("60分", None, 60, 240, "根", "60m", "730d"),
    "日線": ChartTimeframeSpec("日線", None, 50, 200, "日"),
    "週線": ChartTimeframeSpec("週線", "W-FRI", 20, 60, "週"),
    "月線": ChartTimeframeSpec("月線", "ME", 6, 12, "月"),
}

CHART_TIMEFRAME_OPTIONS = tuple(TIMEFRAME_SPECS.keys())
CHART_TIMEFRAME_DEFAULT = "日線"

DISPLAY_RANGES_BY_TIMEFRAME: dict[str, tuple[str, ...]] = {
    "1分": ("1 日", "3 日", "5 日"),
    "5分": ("5 日", "10 日", "20 日"),
    "15分": ("10 日", "20 日", "40 日"),
    "30分": ("10 日", "20 日", "40 日"),
    "60分": ("1 個月", "3 個月", "6 個月"),
    "日線": ("3 個月", "6 個月", "12 個月"),
    "週線": ("1 年", "3 年", "5 年"),
    "月線": ("2 年", "5 年", "10 年"),
}

DISPLAY_RANGE_OFFSET: dict[str, pd.DateOffset] = {
    "1 日": pd.DateOffset(days=1),
    "3 日": pd.DateOffset(days=3),
    "5 日": pd.DateOffset(days=5),
    "10 日": pd.DateOffset(days=10),
    "20 日": pd.DateOffset(days=20),
    "40 日": pd.DateOffset(days=40),
    "1 個月": pd.DateOffset(months=1),
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
    if timeframe in INTRADAY_BAR_MINUTES:
        bar_mins = INTRADAY_BAR_MINUTES[timeframe]
        bars_per_day = max(1, MINUTES_PER_SESSION // bar_mins)
        return max(20, fib_lookback_days * bars_per_day)
    if timeframe == "週線":
        return max(8, round(fib_lookback_days / 5))
    if timeframe == "月線":
        return max(3, round(fib_lookback_days / 21))
    return fib_lookback_days


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


def fetch_intraday_chart_data(symbol: str, timeframe: str) -> pd.DataFrame:
    """向 Yahoo Finance 擷取分 K 資料並計算圖表指標。"""
    spec = TIMEFRAME_SPECS[timeframe]
    if not spec.is_intraday or not spec.yf_interval or not spec.yf_period:
        raise ValueError(f"{timeframe} 非分 K 週期")

    raw = StockFetcher().fetch(
        symbol,
        period=spec.yf_period,
        interval=spec.yf_interval,
    )
    if raw.empty:
        raise ValueError(f"無法取得 {timeframe} 資料，Yahoo 可能暫不提供此週期。")
    return compute_chart_indicators(raw, spec)


def prepare_chart_data(daily_df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """由日線資料產生指定週期圖表 DataFrame（日/週/月）。"""
    spec = TIMEFRAME_SPECS[timeframe]
    if spec.is_intraday:
        raise ValueError(f"{timeframe} 請改用 fetch_intraday_chart_data。")
    if spec.resample_rule is None:
        return daily_df
    base = resample_ohlcv(daily_df, spec.resample_rule)
    if base.empty:
        raise ValueError(f"{timeframe} 資料不足，請延長歷史資料期間。")
    return compute_chart_indicators(base, spec)


def format_chart_index(ts: pd.Timestamp, spec: ChartTimeframeSpec) -> str:
    """格式化圖表索引供 UI 顯示。"""
    t = pd.Timestamp(ts)
    if t.tz is not None:
        t = t.tz_convert("Asia/Taipei")
    if spec.is_intraday:
        return t.strftime("%Y-%m-%d %H:%M")
    return t.strftime("%Y-%m-%d")


def hover_key(ts: pd.Timestamp) -> str:
    """產生 hover 對應鍵（毫秒時間戳，與 Plotly x 軸對齊）。"""
    return str(int(pd.Timestamp(ts).value // 1_000_000))
