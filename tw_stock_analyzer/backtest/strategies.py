"""回測策略：買入訊號產生。"""

from __future__ import annotations

import pandas as pd

from tw_stock_analyzer.predictor.signals import add_composite_direction, add_rsi_oversold_flag


def composite_buy_signals(df: pd.DataFrame) -> pd.Series:
    """
    策略 A：綜合方向看多才買（回測簡化版，僅四項規則、不含 ML）。
    訊號日收盤後判定，次日開盤買入。
    """
    enriched = add_composite_direction(df, use_ml=False)
    return enriched["direction"] == "看多"


def rsi_oversold_buy_signals(df: pd.DataFrame, threshold: float = 30.0) -> pd.Series:
    """
    策略 B：RSI <= 30 時買入。
    訊號日收盤後判定，次日開盤買入。
    """
    enriched = add_rsi_oversold_flag(df, threshold=threshold)
    return enriched["rsi_oversold"]
