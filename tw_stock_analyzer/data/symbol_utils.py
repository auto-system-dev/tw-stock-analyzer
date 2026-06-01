"""股票代號工具。"""

from __future__ import annotations

import re


def normalize_symbol(symbol: str) -> str:
    """將股票代號轉為 Yahoo Finance 格式（例如 2330 -> 2330.TW）。"""
    symbol = symbol.strip().upper()
    if "." in symbol:
        return symbol
    if re.fullmatch(r"\d{4,6}", symbol):
        return f"{symbol}.TW"
    return symbol


def to_stock_id(symbol: str) -> str:
    """台股數字代號（FinMind / 公開資料用）。"""
    return normalize_symbol(symbol).split(".")[0]
