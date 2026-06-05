"""圖表 K 線週期重採樣與指標（僅供圖表顯示，不影響分析引擎）。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD, SMAIndicator
from ta.volatility import BollingerBands

OHLCV_COLS = ("open", "high", "low", "close", "volume")


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


def fib_lookback_bars(timeframe: str, fib_lookback_days: int) -> int:
    """將日線 Fib 波段天數換算為對應週期 K 棒數。"""
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
    """在重採樣後 OHLCV 上計算圖表用指標（保留 NaN 前段以繪製部分均線）。"""
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
    """由日線資料產生指定週期圖表 DataFrame。"""
    spec = TIMEFRAME_SPECS[timeframe]
    if spec.resample_rule is None:
        return daily_df
    base = resample_ohlcv(daily_df, spec.resample_rule)
    if base.empty:
        raise ValueError(f"{timeframe} 資料不足，請延長歷史資料期間。")
    return compute_chart_indicators(base, spec)
