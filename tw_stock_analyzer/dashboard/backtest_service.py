"""儀表板回測服務。"""

from __future__ import annotations

import streamlit as st

from tw_stock_analyzer.backtest.engine import BacktestEngine, ComparisonReport


@st.cache_data(ttl=300, show_spinner=False)
def run_backtest(
    symbol: str,
    period: str,
    hold_days: int,
    strategy: str,
) -> ComparisonReport:
    return BacktestEngine(hold_days=hold_days).run(
        symbol, period=period, strategy=strategy
    )
