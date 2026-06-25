"""主力進出圖表資料快取。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from tw_stock_analyzer.data.broker_main_force import (
    FubonMainForceProvider,
    align_main_force_to_bars,
)


@st.cache_data(ttl=3600, show_spinner=False)
def _load_main_force_history(symbol: str) -> pd.DataFrame | None:
    """快取富邦主力近月買賣張數（約 20 交易日，快取 1 小時）。"""
    return FubonMainForceProvider().fetch_daily_history(symbol)


def load_main_force_for_bars(
    symbol: str,
    bar_index: pd.DatetimeIndex,
) -> pd.DataFrame | None:
    """對齊 K 線的主力買進／賣出／淨張數。"""
    daily = _load_main_force_history(symbol)
    if daily is None or daily.empty:
        return None
    aligned = align_main_force_to_bars(bar_index, daily)
    if aligned["main_force_net"].notna().any():
        return aligned
    return None
