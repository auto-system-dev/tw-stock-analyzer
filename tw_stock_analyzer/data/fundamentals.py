"""基本面資料（EPS、營收、本益比）。"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import yfinance as yf

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.models import FundamentalSnapshot
from tw_stock_analyzer.data.symbol_utils import normalize_symbol, to_stock_id


class FundamentalsProvider:
    """整合 Yahoo Finance 與 FinMind 基本面。"""

    def fetch(self, symbol: str) -> FundamentalSnapshot:
        ticker = normalize_symbol(symbol)
        stock_id = to_stock_id(symbol)
        snap = FundamentalSnapshot()
        notes: list[str] = []

        self._from_yfinance(ticker, snap, notes)
        self._from_finmind(stock_id, snap, notes)
        snap.sources = list(dict.fromkeys(snap.sources))
        return snap

    def _from_yfinance(
        self, ticker: str, snap: FundamentalSnapshot, notes: list[str]
    ) -> None:
        try:
            info = yf.Ticker(ticker).info
            if info.get("trailingPE"):
                snap.pe_ratio = float(info["trailingPE"])
            if info.get("trailingEps"):
                snap.eps = float(info["trailingEps"])
            rev = info.get("totalRevenue")
            if rev:
                snap.revenue_latest = float(rev)
            if snap.pe_ratio or snap.eps:
                snap.sources.append("Yahoo Finance")
        except Exception as e:
            notes.append(f"Yahoo 基本面略過：{e}")

    def _from_finmind(self, stock_id: str, snap: FundamentalSnapshot, notes: list[str]) -> None:
        client = get_finmind_client()

        per = client.fetch("TaiwanStockPER", stock_id, days=30)
        if per is not None and not per.empty:
            row = per.iloc[-1]
            if "PER" in per.columns and pd_notna(row.get("PER")):
                snap.pe_ratio = float(row["PER"])
            if "PBR" in per.columns and pd_notna(row.get("PBR")):
                snap.pb_ratio = float(row["PBR"])
            if "dividend_yield" in per.columns and pd_notna(row.get("dividend_yield")):
                snap.dividend_yield_pct = float(row["dividend_yield"])
            snap.sources.append("FinMind PER/PBR")

        rev = client.fetch("TaiwanStockMonthRevenue", stock_id, days=400)
        if rev is not None and len(rev) >= 2:
            rev = rev.sort_values("date")
            latest = rev.iloc[-1]
            prev_year = rev.iloc[-13] if len(rev) >= 13 else rev.iloc[0]
            if "revenue" in rev.columns:
                snap.revenue_latest = float(latest["revenue"])
                if prev_year["revenue"] and float(prev_year["revenue"]) != 0:
                    snap.revenue_yoy_pct = (
                        (float(latest["revenue"]) - float(prev_year["revenue"]))
                        / float(prev_year["revenue"])
                        * 100
                    )
            snap.sources.append("FinMind 月營收")

        fs = client.get_data(
            "TaiwanStockFinancialStatements",
            stock_id,
            start_date="2020-01-01",
            end_date=datetime.now().date().isoformat(),
        )
        if fs is not None and not fs.empty:
            ni = fs[fs["type"].astype(str).str.contains("NetIncome", case=False, na=False)]
            if not ni.empty:
                snap.eps = snap.eps or float(ni.iloc[-1]["value"])
                snap.sources.append("FinMind 財報")


def pd_notna(val) -> bool:
    return val is not None and pd.notna(val)
