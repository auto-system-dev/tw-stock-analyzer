"""技術訊號與綜合方向（供預測與回測共用）。"""

from __future__ import annotations

import pandas as pd

BULLISH_SIGNALS = {"多頭排列", "超賣", "金叉偏多", "跌破下軌"}
BEARISH_SIGNALS = {"空頭排列", "超買", "死叉偏空", "突破上軌"}


def rule_signals_from_row(row: pd.Series) -> dict[str, str]:
    """單日四項技術規則訊號。"""
    signals: dict[str, str] = {}

    if row["sma_50"] > row["sma_200"]:
        signals["均線"] = "多頭排列"
    elif row["sma_50"] < row["sma_200"]:
        signals["均線"] = "空頭排列"
    else:
        signals["均線"] = "盤整"

    rsi = row["rsi_14"]
    if rsi >= 70:
        signals["RSI"] = "超買"
    elif rsi <= 30:
        signals["RSI"] = "超賣"
    else:
        signals["RSI"] = "中性"

    if row["macd_hist"] > 0 and row["macd"] > row["macd_signal"]:
        signals["MACD"] = "金叉偏多"
    elif row["macd_hist"] < 0 and row["macd"] < row["macd_signal"]:
        signals["MACD"] = "死叉偏空"
    else:
        signals["MACD"] = "中性"

    if row["close"] > row["bb_upper"]:
        signals["布林"] = "突破上軌"
    elif row["close"] < row["bb_lower"]:
        signals["布林"] = "跌破下軌"
    else:
        signals["布林"] = "通道內"

    return signals


def rules_score(signals: dict[str, str]) -> int:
    """僅依技術規則計算加減分。"""
    score = 0
    for sig in signals.values():
        if sig in BULLISH_SIGNALS:
            score += 1
        elif sig in BEARISH_SIGNALS:
            score -= 1
    return score


def aggregate_direction(
    predicted_change: float,
    signals: dict[str, str],
    *,
    use_ml: bool = True,
) -> str:
    """
    綜合方向：看多 / 看空 / 中性。

    use_ml=False 時僅用四項規則（回測簡化版，避免 look-ahead）。
    """
    score = 0
    if use_ml:
        if predicted_change > 0.01:
            score += 2
        elif predicted_change < -0.01:
            score -= 2

    score += rules_score(signals)

    if score >= 2:
        return "看多"
    if score <= -2:
        return "看空"
    return "中性"


def add_composite_direction(df: pd.DataFrame, *, use_ml: bool = False) -> pd.DataFrame:
    """為整段 DataFrame 逐列計算綜合方向（預設僅規則，不含 ML）。"""
    result = df.copy()
    directions = []
    for _, row in result.iterrows():
        signals = rule_signals_from_row(row)
        directions.append(aggregate_direction(0.0, signals, use_ml=use_ml))
    result["direction"] = directions
    return result


def add_rsi_oversold_flag(df: pd.DataFrame, threshold: float = 30.0) -> pd.DataFrame:
    """標記 RSI 超賣日。"""
    result = df.copy()
    result["rsi_oversold"] = result["rsi_14"] <= threshold
    return result
