"""FinMind 日線備援（上櫃/興櫃，或 Yahoo 無資料時）。"""

from __future__ import annotations

import pandas as pd

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.stock_market_registry import to_yahoo_symbol
from tw_stock_analyzer.data.symbol_utils import to_stock_id
from tw_stock_analyzer.data.twse_fetcher import PERIOD_DAYS


class FinMindDailyFetcher:
    """擷取 FinMind TaiwanStockPrice 日 K（成交量為股數）。"""

    def fetch(self, symbol: str, period: str = "2y") -> pd.DataFrame:
        stock_id = to_stock_id(symbol)
        days = PERIOD_DAYS.get(period, PERIOD_DAYS["2y"])
        raw = get_finmind_client().fetch("TaiwanStockPrice", stock_id, days=days)
        if raw is None or raw.empty:
            raise ValueError(f"FinMind 無 {stock_id} 日線資料。")

        df = raw.rename(
            columns={
                "max": "high",
                "min": "low",
                "Trading_Volume": "volume",
            }
        )
        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"FinMind 日線欄位不完整，缺少：{missing}")

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        start = (
            pd.Timestamp.now(tz="Asia/Taipei") - pd.Timedelta(days=days)
        ).tz_localize(None)
        df = df.loc[df.index >= start, required].dropna()
        if df.empty:
            raise ValueError(f"FinMind 在指定期間內無 {stock_id} 日線資料。")

        df.attrs["symbol"] = to_yahoo_symbol(symbol)
        df.attrs["source"] = "finmind"
        return df
