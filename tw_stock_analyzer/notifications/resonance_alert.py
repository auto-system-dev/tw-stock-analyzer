"""多頭共振掃描與 Telegram 訊息格式化。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from tw_stock_analyzer.data.broker_main_force import resolve_fetch_main_force
from tw_stock_analyzer.data.fetcher import StockFetcher
from tw_stock_analyzer.data.stock_names import resolve_tw_stock_name
from tw_stock_analyzer.indicators.fibonacci import (
    FIB_SIGNAL_LOOKBACK,
    compute_fibonacci_retracement,
)
from tw_stock_analyzer.indicators.technical import TechnicalIndicators
from tw_stock_analyzer.predictor.resonance import (
    BullishResonance,
    RESONANCE_ITEM_COUNT,
    compute_bullish_resonance,
)
from tw_stock_analyzer.screener.engine import ScreenerEngine
from tw_stock_analyzer.screener.filters import ScreenerFilters
from tw_stock_analyzer.screener.universe import get_universe

# 全市場掃描每批檔數（避免長時間無回饋、降低單次記憶體峰值）
RESONANCE_BATCH_SIZE = 50
# 潛力股 Top N → 多頭共振（含第 7 項）預設候選檔數
DEFAULT_TOP_RESONANCE_CANDIDATES = 60
# Telegram 單則訊息最多列出幾檔符合標的（避免超過 4096 字元限制）
TELEGRAM_MAX_HITS = 20


@dataclass(frozen=True)
class ResonanceHit:
    symbol: str
    name: str
    close: float
    trade_date: datetime
    resonance: BullishResonance

    @property
    def label(self) -> str:
        return f"{self.resonance.passed_count}/{self.resonance.total}"


@dataclass(frozen=True)
class ResonanceScanSummary:
    """掃描摘要（供 CLI / Telegram 顯示進度與合併結果）。"""

    hits: tuple[ResonanceHit, ...]
    scanned_count: int
    total_count: int
    batch_count: int
    fetch_main_force: bool = False


def _chunked(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _merge_hits(hits: list[ResonanceHit]) -> list[ResonanceHit]:
    """合併分批結果；同一代號保留共振分數較高者。"""
    best: dict[str, ResonanceHit] = {}
    for hit in hits:
        prev = best.get(hit.symbol)
        if prev is None or hit.resonance.passed_count > prev.resonance.passed_count:
            best[hit.symbol] = hit
    return list(best.values())


def _scan_stock_ids(
    stock_ids: list[str],
    *,
    fetcher: StockFetcher,
    indicators: TechnicalIndicators,
    min_passed: int,
    period: str,
    fetch_main_force: bool,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[ResonanceHit]:
    hits: list[ResonanceHit] = []
    total = len(stock_ids)
    for idx, stock_id in enumerate(stock_ids, start=1):
        if on_progress is not None:
            on_progress(idx, total)
        try:
            raw = fetcher.fetch(stock_id, period=period)
            if len(raw) < 2:
                continue
            enriched = indicators.compute(raw)
            fib = compute_fibonacci_retracement(enriched, lookback=FIB_SIGNAL_LOOKBACK)
            resonance = compute_bullish_resonance(
                enriched,
                fib,
                symbol=stock_id,
                fetch_main_force=fetch_main_force,
            )
            if resonance.passed_count < min_passed:
                continue
            latest = enriched.iloc[-1]
            trade_date = pd.Timestamp(enriched.index[-1]).to_pydatetime()
            hits.append(
                ResonanceHit(
                    symbol=stock_id,
                    name=resolve_tw_stock_name(stock_id),
                    close=float(latest["close"]),
                    trade_date=trade_date,
                    resonance=resonance,
                )
            )
        except Exception:
            continue
    return hits


def scan_resonance_hits(
    *,
    universe: str = "watchlist",
    symbols: list[str] | None = None,
    min_passed: int = 5,
    period: str = "1y",
    batch_size: int = RESONANCE_BATCH_SIZE,
    fetch_main_force: bool | None = None,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> list[ResonanceHit]:
    """掃描股票池，回傳多頭共振達門檻的標的。

    全市場（universe=all）且檔數超過 batch_size 時，分批掃描後合併結果。
    on_progress(scanned, total, batch_index) 於每批完成後呼叫。
    """
    summary = scan_resonance_with_summary(
        universe=universe,
        symbols=symbols,
        min_passed=min_passed,
        period=period,
        batch_size=batch_size,
        fetch_main_force=fetch_main_force,
        on_progress=on_progress,
    )
    return list(summary.hits)


def scan_resonance_with_summary(
    *,
    universe: str = "watchlist",
    symbols: list[str] | None = None,
    min_passed: int = 5,
    period: str = "1y",
    batch_size: int = RESONANCE_BATCH_SIZE,
    fetch_main_force: bool | None = None,
    on_progress: Callable[[int, int, int], None] | None = None,
) -> ResonanceScanSummary:
    """掃描並回傳合併結果與掃描摘要。"""
    stock_ids, _ = get_universe(universe, symbols)
    total = len(stock_ids)
    use_main_force = resolve_fetch_main_force(fetch_main_force, total)
    fetcher = StockFetcher()
    indicators = TechnicalIndicators()
    all_hits: list[ResonanceHit] = []

    use_batches = (
        universe == "all"
        and not symbols
        and total > batch_size
    )
    batches = _chunked(stock_ids, batch_size) if use_batches else [stock_ids]
    scanned = 0

    for batch_index, batch in enumerate(batches, start=1):
        all_hits.extend(
            _scan_stock_ids(
                batch,
                fetcher=fetcher,
                indicators=indicators,
                min_passed=min_passed,
                period=period,
                fetch_main_force=use_main_force,
            )
        )
        scanned += len(batch)
        if on_progress is not None:
            on_progress(scanned, total, batch_index)

    merged = _merge_hits(all_hits)
    merged.sort(key=lambda h: (h.resonance.passed_count, h.symbol), reverse=True)
    return ResonanceScanSummary(
        hits=tuple(merged),
        scanned_count=scanned,
        total_count=total,
        batch_count=len(batches),
        fetch_main_force=use_main_force,
    )


def scan_top_resonance_with_summary(
    *,
    universe: str = "all",
    symbols: list[str] | None = None,
    top_n: int = DEFAULT_TOP_RESONANCE_CANDIDATES,
    min_passed: int = 6,
    period: str = "1y",
    min_score: int = 0,
    bullish_only: bool = False,
    on_screener_progress: Callable[[str, int, int], None] | None = None,
    on_resonance_progress: Callable[[int, int], None] | None = None,
) -> tuple[ResonanceScanSummary, str]:
    """全市場潛力股 Top N → 多頭共振（強制含第 7 項主力淨張）。

    回傳 (掃描摘要, 股票池標籤)。
    """
    if symbols:
        candidate_ids = list(symbols)
        _, base_label = get_universe(universe, symbols)
        universe_total = len(candidate_ids)
        batch_count = 1
    else:
        flt = ScreenerFilters(
            min_score=min_score,
            top_n=top_n,
            deep_candidates=top_n,
            bullish_only=bullish_only,
        )
        screener = ScreenerEngine(period=period, fetch_main_force=False)
        screen_result = screener.scan(
            universe=universe,
            filters=flt,
            progress=on_screener_progress,
        )
        candidate_ids = [row.symbol for row in screen_result.ranked]
        universe_total = screen_result.universe_total or screen_result.scanned_count
        batch_count = screen_result.batch_count
        base_label = screen_result.universe_label

    pool_label = (
        f"{base_label} → 潛力股 Top {len(candidate_ids)}"
        if not symbols
        else f"自訂 {len(candidate_ids)} 檔"
    )

    fetcher = StockFetcher()
    indicators = TechnicalIndicators()
    resonance_total = len(candidate_ids)

    hits = _scan_stock_ids(
        candidate_ids,
        fetcher=fetcher,
        indicators=indicators,
        min_passed=min_passed,
        period=period,
        fetch_main_force=True,
        on_progress=on_resonance_progress,
    )

    merged = _merge_hits(hits)
    merged.sort(key=lambda h: (h.resonance.passed_count, h.symbol), reverse=True)
    summary = ResonanceScanSummary(
        hits=tuple(merged),
        scanned_count=resonance_total,
        total_count=universe_total,
        batch_count=batch_count,
        fetch_main_force=True,
    )
    return summary, pool_label


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_resonance_telegram_message(
    hits: list[ResonanceHit],
    *,
    min_passed: int,
    universe_label: str,
    scanned_count: int | None = None,
    total_count: int | None = None,
    fetch_main_force: bool = True,
    title: str = "多頭共振掃描",
) -> str:
    """將掃描結果格式化為 Telegram HTML 訊息。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    scan_note = ""
    if scanned_count is not None and total_count is not None and total_count > 0:
        scan_note = f"\n已掃描 {scanned_count}/{total_count} 檔"
    main_force_note = (
        ""
        if fetch_main_force
        else f"\n第 7 項主力淨張：本次掃描略過"
    )

    if not hits:
        return (
            f"📊 <b>{_escape_html(title)}</b>（{now}）\n"
            f"股票池：{_escape_html(universe_label)}{scan_note}{main_force_note}\n"
            f"門檻：≥ {min_passed}/{RESONANCE_ITEM_COUNT}\n"
            f"\n今日無符合條件的標的。"
        )

    display_hits = hits[:TELEGRAM_MAX_HITS]
    truncated = len(hits) > len(display_hits)

    lines = [
        f"📊 <b>{_escape_html(title)}</b>（{now}）",
        f"股票池：{_escape_html(universe_label)}{scan_note}{main_force_note}",
        f"門檻：≥ {min_passed}/{RESONANCE_ITEM_COUNT}",
        f"符合 <b>{len(hits)}</b> 檔"
        + (f"（以下顯示前 {len(display_hits)} 檔）" if truncated else "")
        + "：",
        "",
    ]
    for hit in display_hits:
        lines.append(
            f"🟢 <b>{_escape_html(hit.name)}</b>（{hit.symbol}）"
            f" · <b>{hit.label}</b> · 收 {hit.close:,.0f}"
        )
        for item in hit.resonance.items:
            mark = "✅" if item.passed else "❌"
            lines.append(f"  {mark} {_escape_html(item.label)}")
        lines.append("")

    lines.append("<i>僅供研究參考，不構成投資建議。</i>")
    return "\n".join(lines).strip()
