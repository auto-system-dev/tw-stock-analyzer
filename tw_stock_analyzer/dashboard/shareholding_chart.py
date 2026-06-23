"""集保千張大戶比例資料快取。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tw_stock_analyzer.data.shareholding import ShareholdingProvider


@st.cache_data(ttl=3600, show_spinner=False)
def _load_over_1000_ratio_history(symbol: str) -> pd.DataFrame | None:
    """快取集保千張大戶比例（每週更新，快取 1 小時）。"""
    df = ShareholdingProvider(weeks=26).fetch_over_1000_ratio_history(symbol)
    if df is None or df.empty:
        return None
    return df.copy()
