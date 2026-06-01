"""儀表板用的分析服務（可獨立於 Streamlit UI 匯入）。"""

from __future__ import annotations

import streamlit as st

from tw_stock_analyzer.analyzer.engine import AnalysisReport, StockAnalyzer


@st.cache_data(ttl=300, show_spinner=False)
def run_analysis(symbol: str, period: str, horizon_days: int) -> AnalysisReport:
    return StockAnalyzer(horizon_days=horizon_days).analyze(symbol, period=period)
