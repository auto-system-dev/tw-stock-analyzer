"""三大法人籌碼。"""

from __future__ import annotations

import pandas as pd

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.models import InstitutionalFlow
from tw_stock_analyzer.data.symbol_utils import to_stock_id


class InstitutionalProvider:
    """外資、投信、自營商近 N 日淨買超。"""

    def __init__(self, period_days: int = 5):
        self.period_days = period_days

    def fetch(self, symbol: str) -> InstitutionalFlow | None:
        stock_id = to_stock_id(symbol)
        client = get_finmind_client()
        df = client.fetch(
            "TaiwanStockInstitutionalInvestorsBuySell",
            stock_id,
            days=max(self.period_days * 3, 30),
        )
        if df is None or df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        recent_dates = sorted(df["date"].unique())[-self.period_days :]
        df = df[df["date"].isin(recent_dates)]

        foreign = _net_by_name(df, "Foreign_Investor")
        trust = _net_by_name(df, "Investment_Trust")
        dealer = _net_by_name(df, "Dealer_self")

        return InstitutionalFlow(
            period_days=self.period_days,
            foreign_net=foreign,
            trust_net=trust,
            dealer_net=dealer,
            total_net=foreign + trust + dealer,
            latest_date=str(recent_dates[-1].date()) if len(recent_dates) else "—",
            sources=["FinMind 三大法人"],
        )


def _net_by_name(df: pd.DataFrame, name: str) -> float:
    sub = df[df["name"] == name]
    if sub.empty or "buy" not in sub.columns or "sell" not in sub.columns:
        return 0.0
    return float((sub["buy"] - sub["sell"]).sum())
