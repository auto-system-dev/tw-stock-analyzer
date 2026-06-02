"""儀表板用的掃描服務。"""

from __future__ import annotations

import streamlit as st

from tw_stock_analyzer.screener.engine import ScreenerEngine
from tw_stock_analyzer.screener.filters import ScreenerFilters
from tw_stock_analyzer.screener.models import ScreenerResult


@st.cache_data(ttl=600, show_spinner=False)
def run_screen(
    universe: str,
    symbols_csv: str,
    top_n: int,
    min_score: int,
    bullish_only: bool,
    period: str,
) -> ScreenerResult:
    sym_list = [s.strip() for s in symbols_csv.split(",") if s.strip()] or None
    flt = ScreenerFilters(
        min_score=min_score,
        top_n=top_n,
        bullish_only=bullish_only,
    )
    return ScreenerEngine(period=period).scan(
        universe=universe,
        symbols=sym_list,
        filters=flt,
    )
