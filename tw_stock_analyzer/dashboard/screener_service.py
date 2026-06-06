"""儀表板用的掃描服務。"""

from __future__ import annotations

from collections.abc import Callable

from tw_stock_analyzer.screener.engine import ScreenerEngine
from tw_stock_analyzer.screener.filters import ScreenerFilters
from tw_stock_analyzer.screener.models import ScreenerResult


def build_screener_filters(
    *,
    top_n: int,
    min_score: int,
    bullish_only: bool,
    resonance_full_only: bool = False,
    resonance_min_4: bool = False,
) -> ScreenerFilters:
    return ScreenerFilters(
        min_score=min_score,
        top_n=top_n,
        bullish_only=bullish_only,
        resonance_full_only=resonance_full_only,
        resonance_min=4 if resonance_min_4 and not resonance_full_only else None,
    )


def run_screen_live(
    universe: str,
    symbols_csv: str,
    top_n: int,
    min_score: int,
    bullish_only: bool,
    period: str,
    *,
    resonance_full_only: bool = False,
    resonance_min_4: bool = False,
    progress: Callable[[str, int, int], None] | None = None,
) -> ScreenerResult:
    """執行掃描（不快取），支援進度回呼以保持 Streamlit 連線。"""
    sym_list = [s.strip() for s in symbols_csv.split(",") if s.strip()] or None
    flt = build_screener_filters(
        top_n=top_n,
        min_score=min_score,
        bullish_only=bullish_only,
        resonance_full_only=resonance_full_only,
        resonance_min_4=resonance_min_4,
    )
    return ScreenerEngine(period=period, lightweight_deep=True).scan(
        universe=universe,
        symbols=sym_list,
        filters=flt,
        progress=progress,
    )
