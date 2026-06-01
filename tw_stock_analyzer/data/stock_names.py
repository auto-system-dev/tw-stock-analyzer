"""台股中文名稱解析（FinMind + 常用標的對照）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import lru_cache

from tw_stock_analyzer.data.finmind_client import get_finmind_client
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


@lru_cache(maxsize=1024)
def _fetch_name_from_finmind(stock_id: str) -> str | None:
    client = get_finmind_client()
    end = datetime.now().date()
    start = end - timedelta(days=60)
    df = client.get_data(
        "TaiwanStockInfo",
        stock_id,
        start.isoformat(),
        end.isoformat(),
    )
    if df is None or df.empty or "stock_name" not in df.columns:
        return None
    name = str(df.iloc[-1]["stock_name"]).strip()
    return name or None


def resolve_tw_stock_name(symbol: str, fallback: str = "") -> str:
    """
    將代號解析為中文公司名。

    優先順序：FinMind TaiwanStockInfo → 常用對照表 → fallback（如 Yahoo 英文名）→ 代號。
    """
    stock_id = to_stock_id(symbol)
    finmind_name = _fetch_name_from_finmind(stock_id)
    if finmind_name:
        return finmind_name
    if stock_id in COMMON_TW_STOCK_NAMES:
        return COMMON_TW_STOCK_NAMES[stock_id]
    fb = (fallback or "").strip()
    return fb if fb and fb != "—" else stock_id
