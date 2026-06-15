"""台股代號與交易市場對照（FinMind TaiwanStockInfo）。"""

from __future__ import annotations

from functools import lru_cache

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.symbol_utils import to_stock_id

YAHOO_SUFFIX_BY_MARKET: dict[str, str] = {
    "twse": ".TW",
    "tpex": ".TWO",
    "emerging": ".TWO",
}


@lru_cache(maxsize=1)
def fetch_stock_market_map() -> dict[str, str]:
    """stock_id -> twse | tpex | emerging。"""
    df = get_finmind_client().fetch_dataset("TaiwanStockInfo")
    if df is None or df.empty:
        return {}
    id_col = "stock_id" if "stock_id" in df.columns else "data_id"
    if id_col not in df.columns or "type" not in df.columns:
        return {}
    subset = df[[id_col, "type"]].copy()
    subset[id_col] = subset[id_col].astype(str).str.strip()
    subset["type"] = subset["type"].astype(str).str.strip().str.lower()
    subset = subset[subset[id_col].str.match(r"^\d{4}$", na=False)]
    return dict(zip(subset[id_col], subset["type"], strict=False))


def lookup_market_type(symbol: str) -> str | None:
    """查詢代號所屬市場；未知時回傳 None。"""
    return fetch_stock_market_map().get(to_stock_id(symbol))


def to_yahoo_symbol(symbol: str) -> str:
    """依市場回傳 Yahoo Finance 代號（上市 .TW、上櫃/興櫃 .TWO）。"""
    text = symbol.strip().upper()
    if "." in text:
        return text
    stock_id = to_stock_id(text)
    market = lookup_market_type(stock_id)
    suffix = YAHOO_SUFFIX_BY_MARKET.get(market or "", ".TW")
    return f"{stock_id}{suffix}"


def is_twse_listed(symbol: str) -> bool:
    """是否為上市個股（可用 TWSE 日線 API）。"""
    market = lookup_market_type(symbol)
    return market in (None, "twse")
