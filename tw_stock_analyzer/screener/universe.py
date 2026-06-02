"""股票池定義。"""

from __future__ import annotations

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.stock_names import COMMON_TW_STOCK_NAMES, resolve_tw_stock_name

WATCHLIST_SYMBOLS: list[str] = [
    *COMMON_TW_STOCK_NAMES.keys(),
    "1301",
    "1303",
    "2002",
    "2207",
    "2886",
    "2890",
    "2912",
    "3034",
    "3231",
    "3443",
    "3661",
    "5871",
    "6669",
    "6770",
    "8046",
    "9910",
]


def get_watchlist() -> list[str]:
    """常用股 / 權值股清單。"""
    return sorted(set(WATCHLIST_SYMBOLS))


def get_universe(universe: str, symbols: list[str] | None = None) -> tuple[list[str], str]:
    """
    解析股票池。

    Returns:
        (代號清單, 顯示標籤)
    """
    if symbols:
        cleaned = sorted({s.strip() for s in symbols if s.strip()})
        return cleaned, f"自訂 ({len(cleaned)} 檔)"

    if universe == "watchlist":
        wl = get_watchlist()
        return wl, f"常用股 ({len(wl)} 檔)"

    if universe == "all":
        finmind_list = get_finmind_client().fetch_stock_list()
        if finmind_list:
            return finmind_list, f"全市場 ({len(finmind_list)} 檔)"
        wl = get_watchlist()
        return wl, f"常用股備援 ({len(wl)} 檔，FinMind 無法取得全市場)"

    raise ValueError(f"未知股票池：{universe}")


def resolve_name(symbol: str) -> str:
    return resolve_tw_stock_name(symbol)
