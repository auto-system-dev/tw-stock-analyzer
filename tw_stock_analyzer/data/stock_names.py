"""台股中文名稱解析（FinMind + 常用標的對照）。"""

from __future__ import annotations

from tw_stock_analyzer.data.stock_market_registry import fetch_stock_name_map
from tw_stock_analyzer.data.symbol_utils import to_stock_id

# 側欄常用標的與常見權值股；FinMind 不可用時的離線備援
COMMON_TW_STOCK_NAMES: dict[str, str] = {
    "2330": "台積電",
    "2317": "鴻海",
    "2454": "聯發科",
    "2303": "聯電",
    "2881": "富邦金",
    "2308": "台達電",
    "2412": "中華電",
    "2882": "國泰金",
    "2891": "中信金",
    "2892": "第一金",
    "3711": "日月光投控",
    "2382": "廣達",
    "3008": "大立光",
}


def _has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def resolve_tw_stock_name(symbol: str, fallback: str = "") -> str:
    """
    將代號解析為中文公司名。

    優先順序：常用對照表 → FinMind TaiwanStockInfo 快取 → 含中文的 fallback → 代號。
    不使用 Yahoo 等來源的純英文名稱，避免儀表板 / Telegram 顯示英文公司全名。
    """
    stock_id = to_stock_id(symbol)
    if stock_id in COMMON_TW_STOCK_NAMES:
        return COMMON_TW_STOCK_NAMES[stock_id]

    finmind_name = fetch_stock_name_map().get(stock_id, "").strip()
    if finmind_name:
        return finmind_name

    fb = (fallback or "").strip()
    if fb and fb != "—" and _has_cjk(fb):
        return fb
    return stock_id
