"""台股代號與交易市場對照（FinMind TaiwanStockInfo）。"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.symbol_utils import to_stock_id

YAHOO_SUFFIX_BY_MARKET: dict[str, str] = {
    "twse": ".TW",
    "tpex": ".TWO",
    "emerging": ".TWO",
}

# FinMind 清單若超過此天數未更新，視為已下市並排除於全市場掃描
ACTIVE_LISTING_MAX_STALE_DAYS = 7


@lru_cache(maxsize=1)
def _latest_stock_info_rows() -> pd.DataFrame:
    """每股一列（最新 date），僅含 4 位數代號。"""
    df = get_finmind_client().fetch_dataset("TaiwanStockInfo")
    empty = pd.DataFrame(columns=["stock_id", "type", "industry_category", "date"])
    if df is None or df.empty:
        return empty

    id_col = "stock_id" if "stock_id" in df.columns else "data_id"
    if id_col not in df.columns:
        return empty

    subset = df.copy()
    subset["stock_id"] = subset[id_col].astype(str).str.strip()
    subset = subset[subset["stock_id"].str.match(r"^\d{4}$", na=False)]
    if subset.empty:
        return empty

    if "date" in subset.columns:
        subset["date"] = pd.to_datetime(subset["date"])
        subset = subset.sort_values("date").groupby("stock_id", as_index=False).tail(1)

    cols = ["stock_id"]
    for col in ("type", "industry_category", "date"):
        if col in subset.columns:
            cols.append(col)
    return subset[cols].reset_index(drop=True)


@lru_cache(maxsize=1)
def fetch_active_stock_ids() -> list[str]:
    """目前在市標的（FinMind 近 N 日仍有更新）。"""
    df = _latest_stock_info_rows()
    if df.empty:
        return []
    if "date" not in df.columns:
        return sorted(df["stock_id"].unique().tolist())

    latest_global = df["date"].max()
    cutoff = latest_global - pd.Timedelta(days=ACTIVE_LISTING_MAX_STALE_DAYS)
    active = df.loc[df["date"] >= cutoff, "stock_id"]
    return sorted(active.unique().tolist())


@lru_cache(maxsize=1)
def fetch_stock_market_map() -> dict[str, str]:
    """stock_id -> twse | tpex | emerging。"""
    df = _latest_stock_info_rows()
    if df.empty or "type" not in df.columns:
        return {}
    types = df["type"].astype(str).str.strip().str.lower()
    return dict(zip(df["stock_id"], types, strict=False))


@lru_cache(maxsize=1)
def fetch_stock_industry_map() -> dict[str, str]:
    """stock_id -> industry_category（如 ETF）。"""
    df = _latest_stock_info_rows()
    if df.empty or "industry_category" not in df.columns:
        return {}
    industries = df["industry_category"].astype(str).str.strip()
    return dict(zip(df["stock_id"], industries, strict=False))


def lookup_market_type(symbol: str) -> str | None:
    """查詢代號所屬市場；未知時回傳 None。"""
    return fetch_stock_market_map().get(to_stock_id(symbol))


def is_etf(symbol: str) -> bool:
    """是否為 ETF（TWSE 個股日線 API 不支援）。"""
    industry = fetch_stock_industry_map().get(to_stock_id(symbol), "")
    return industry.upper() == "ETF"


def is_active_listing(symbol: str) -> bool:
    """是否為 FinMind 現行在市標的。"""
    return to_stock_id(symbol) in set(fetch_active_stock_ids())


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
    """是否為上市個股（可用 TWSE 日線 API；不含 ETF）。"""
    market = lookup_market_type(symbol)
    if market not in (None, "twse"):
        return False
    if is_etf(symbol):
        return False
    return True
