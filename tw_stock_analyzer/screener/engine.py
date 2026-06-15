"""批次潛力股掃描引擎（兩階段）。"""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from tw_stock_analyzer.analyzer.scoring import compute_potential_score
from tw_stock_analyzer.data.fetcher import StockFetcher
from tw_stock_analyzer.data.market_context import MarketContextProvider
from tw_stock_analyzer.indicators.fibonacci import (
    FIB_SIGNAL_LOOKBACK,
    compute_fibonacci_retracement,
)
from tw_stock_analyzer.indicators.technical import TechnicalIndicators
from tw_stock_analyzer.predictor.resonance import compute_bullish_resonance
from tw_stock_analyzer.predictor.signals import (
    aggregate_direction,
    rule_signals_from_row,
    rules_score,
)
from tw_stock_analyzer.screener.filters import ScreenerFilters
from tw_stock_analyzer.screener.models import RankedStock, ScreenerResult
from tw_stock_analyzer.data.stock_market_registry import fetch_stock_market_map
from tw_stock_analyzer.screener.universe import get_universe, resolve_name

# 全市場分批掃描每批檔數（儀表板 / CLI 共用）
SCREENER_BATCH_SIZE = 50

FastRow = tuple[str, int, dict[str, str], pd.Series, pd.DataFrame]


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class ScreenerEngine:
    """兩階段掃描：快速技術篩選 → 深度基本面/籌碼評分。"""

    def __init__(
        self,
        *,
        period: str = "1y",
        institutional_days: int = 5,
        lightweight_deep: bool = False,
        batch_size: int = SCREENER_BATCH_SIZE,
    ):
        self.fetcher = StockFetcher()
        self.indicators = TechnicalIndicators()
        self.market = MarketContextProvider(institutional_days=institutional_days)
        self.period = period
        self.lightweight_deep = lightweight_deep
        self.batch_size = batch_size

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

    def _fast_scan_ids(
        self,
        stock_ids: list[str],
        *,
        progress: Callable[[str, int, int], None] | None,
        progress_offset: int,
        progress_total: int,
    ) -> list[FastRow]:
        rows: list[FastRow] = []
        for local_idx, stock_id in enumerate(stock_ids, start=1):
            global_idx = progress_offset + local_idx
            if progress:
                progress("fast", global_idx, progress_total)
            try:
                raw = self.fetcher.fetch(stock_id, period=self.period)
                enriched = self.indicators.compute(raw)
                if enriched.empty:
                    continue
                latest = enriched.iloc[-1]
                signals = rule_signals_from_row(latest)
                fast = self._fast_score(latest, signals)
                rows.append((stock_id, fast, signals, latest, enriched))
            except Exception:
                continue
        return rows

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
        universe_total = len(stock_ids)

        if symbols:
            notes.append(f"已使用自訂代號（{len(stock_ids)} 檔），股票池設定已覆蓋")

        use_batches = (
            universe == "all"
            and not symbols
            and universe_total > self.batch_size
        )
        batches = (
            _chunked(stock_ids, self.batch_size) if use_batches else [stock_ids]
        )
        if use_batches:
            market_map = fetch_stock_market_map()
            twse_n = sum(1 for s in stock_ids if market_map.get(s) == "twse")
            tpex_n = sum(1 for s in stock_ids if market_map.get(s) == "tpex")
            emerging_n = sum(1 for s in stock_ids if market_map.get(s) == "emerging")
            notes.append(
                f"全市場分批掃描（每批 {self.batch_size} 檔，共 {len(batches)} 批），"
                f"預計需 {universe_total} 檔 × 數秒，請耐心等候"
            )
            if twse_n or tpex_n or emerging_n:
                notes.append(
                    f"市場組成：上市 {twse_n}、上櫃 {tpex_n}、興櫃 {emerging_n} 檔"
                    f"（上櫃/興櫃使用 .TWO 代號）"
                )

        if universe == "all" and "備援" in label:
            notes.append("FinMind 全市場清單不可用，已改用常用股清單")

        fast_rows: list[FastRow] = []
        scanned_offset = 0
        for batch in batches:
            fast_rows.extend(
                self._fast_scan_ids(
                    batch,
                    progress=progress,
                    progress_offset=scanned_offset,
                    progress_total=universe_total,
                )
            )
            scanned_offset += len(batch)

        fast_rows.sort(key=lambda x: x[1], reverse=True)
        candidates = fast_rows[: flt.deep_candidates]

        ranked: list[RankedStock] = []
        deep_total = len(candidates)

        for idx, (stock_id, fast, signals, latest, enriched) in enumerate(candidates, start=1):
            if progress:
                progress("deep", idx, deep_total)
            try:
                name = resolve_name(stock_id)
                ctx = self.market.fetch(
                    stock_id, name, lightweight=self.lightweight_deep
                )
                score = compute_potential_score(
                    latest,
                    signals,
                    ctx,
                    prediction=None,
                    use_ml=False,
                )
                direction = aggregate_direction(0.0, signals, use_ml=False)
                revenue_yoy = ctx.fundamentals.revenue_yoy_pct
                fib = compute_fibonacci_retracement(enriched, lookback=FIB_SIGNAL_LOOKBACK)
                resonance = compute_bullish_resonance(enriched, fib)
                if not flt.passes(
                    score.total,
                    direction,
                    revenue_yoy,
                    resonance_passed=resonance.passed_count,
                    resonance_total=resonance.total,
                ):
                    continue
                ranked.append(
                    RankedStock(
                        symbol=stock_id,
                        name=name,
                        score=score,
                        direction=direction,
                        fast_score=fast,
                        resonance_passed=resonance.passed_count,
                        resonance_total=resonance.total,
                    )
                )
            except Exception:
                continue

        ranked.sort(key=lambda r: r.score.total, reverse=True)
        ranked = ranked[: flt.top_n]

        success_count = len(fast_rows)
        return ScreenerResult(
            universe_label=label,
            universe_total=universe_total,
            scanned_count=success_count,
            skipped_count=max(0, universe_total - success_count),
            deep_scanned_count=deep_total,
            batch_count=len(batches),
            ranked=ranked,
            notes=notes,
        )
