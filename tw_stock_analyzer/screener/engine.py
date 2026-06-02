"""批次潛力股掃描引擎（兩階段）。"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from tw_stock_analyzer.analyzer.scoring import compute_potential_score
from tw_stock_analyzer.data.fetcher import StockFetcher
from tw_stock_analyzer.data.market_context import MarketContextProvider
from tw_stock_analyzer.indicators.technical import TechnicalIndicators
from tw_stock_analyzer.predictor.signals import (
    aggregate_direction,
    rule_signals_from_row,
    rules_score,
)
from tw_stock_analyzer.screener.filters import ScreenerFilters
from tw_stock_analyzer.screener.models import RankedStock, ScreenerResult
from tw_stock_analyzer.screener.universe import get_universe, resolve_name


class ScreenerEngine:
    """兩階段掃描：快速技術篩選 → 深度基本面/籌碼評分。"""

    def __init__(
        self,
        *,
        period: str = "1y",
        institutional_days: int = 5,
    ):
        self.fetcher = StockFetcher()
        self.indicators = TechnicalIndicators()
        self.market = MarketContextProvider(institutional_days=institutional_days)
        self.period = period

    def _fast_score(self, latest: pd.Series, signals: dict[str, str]) -> int:
        """快速分：技術規則 + 動能（不含 ML 與 API）。"""
        raw = rules_score(signals)
        base = int((raw + 4) / 8 * 20)
        base = max(0, min(20, base))

        momentum = 0
        vol_ratio = float(latest.get("volume_ratio_5d", 1.0))
        if vol_ratio > 1.5:
            momentum += 5
        elif vol_ratio > 1.2:
            momentum += 3

        pct_high = float(latest.get("pct_from_52w_high", -1.0))
        if pct_high > -0.10:
            momentum += 5
        elif pct_high > -0.20:
            momentum += 3

        if signals.get("均線") == "多頭排列":
            momentum += 5

        return base + min(15, momentum)

    def scan(
        self,
        universe: str = "watchlist",
        symbols: list[str] | None = None,
        filters: ScreenerFilters | None = None,
        progress: Callable[[str, int, int], None] | None = None,
    ) -> ScreenerResult:
        """執行兩階段掃描並回傳排名結果。"""
        flt = filters or ScreenerFilters()
        stock_ids, label = get_universe(universe, symbols)
        notes: list[str] = []

        if universe == "all" and "備援" in label:
            notes.append("FinMind 全市場清單不可用，已改用常用股清單")

        fast_rows: list[tuple[str, int, dict[str, str], pd.Series]] = []
        total = len(stock_ids)

        for idx, stock_id in enumerate(stock_ids, start=1):
            if progress:
                progress("fast", idx, total)
            try:
                raw = self.fetcher.fetch(stock_id, period=self.period)
                enriched = self.indicators.compute(raw)
                if enriched.empty:
                    continue
                latest = enriched.iloc[-1]
                signals = rule_signals_from_row(latest)
                fast = self._fast_score(latest, signals)
                fast_rows.append((stock_id, fast, signals, latest))
            except Exception:
                continue

        fast_rows.sort(key=lambda x: x[1], reverse=True)
        candidates = fast_rows[: flt.deep_candidates]

        ranked: list[RankedStock] = []
        deep_total = len(candidates)

        for idx, (stock_id, fast, signals, latest) in enumerate(candidates, start=1):
            if progress:
                progress("deep", idx, deep_total)
            try:
                name = resolve_name(stock_id)
                ctx = self.market.fetch(stock_id, name)
                score = compute_potential_score(
                    latest,
                    signals,
                    ctx,
                    prediction=None,
                    use_ml=False,
                )
                direction = aggregate_direction(0.0, signals, use_ml=False)
                revenue_yoy = ctx.fundamentals.revenue_yoy_pct
                if not flt.passes(score.total, direction, revenue_yoy):
                    continue
                ranked.append(
                    RankedStock(
                        symbol=stock_id,
                        name=name,
                        score=score,
                        direction=direction,
                        fast_score=fast,
                    )
                )
            except Exception:
                continue

        ranked.sort(key=lambda r: r.score.total, reverse=True)
        ranked = ranked[: flt.top_n]

        return ScreenerResult(
            universe_label=label,
            scanned_count=len(fast_rows),
            deep_scanned_count=deep_total,
            ranked=ranked,
            notes=notes,
        )
