"""股票代號工具。"""

from __future__ import annotations

import re


def normalize_symbol(symbol: str) -> str:
    """將股票代號轉為 Yahoo Finance 格式（依市場自動選 .TW / .TWO）。"""
    symbol = symbol.strip().upper()
    if "." in symbol:
        return symbol
    if re.fullmatch(r"\d{4,6}", symbol):
        from tw_stock_analyzer.data.stock_market_registry import to_yahoo_symbol

        return to_yahoo_symbol(symbol)
    return symbol


def to_stock_id(symbol: str) -> str:
    """台股數字代號（FinMind / 公開資料用）。"""
    text = symbol.strip().upper()
    if "." in text:
        return text.split(".")[0]
    return text
