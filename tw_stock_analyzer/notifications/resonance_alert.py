"""多頭共振掃描與 Telegram 訊息格式化。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from tw_stock_analyzer.data.fetcher import StockFetcher
from tw_stock_analyzer.data.stock_names import resolve_tw_stock_name
from tw_stock_analyzer.indicators.fibonacci import (
    FIB_SIGNAL_LOOKBACK,
    compute_fibonacci_retracement,
)
from tw_stock_analyzer.indicators.technical import TechnicalIndicators
from tw_stock_analyzer.predictor.resonance import BullishResonance, compute_bullish_resonance
from tw_stock_analyzer.screener.universe import get_universe


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


def scan_resonance_hits(
    *,
    universe: str = "watchlist",
    symbols: list[str] | None = None,
    min_passed: int = 5,
    period: str = "1y",
) -> list[ResonanceHit]:
    """掃描股票池，回傳多頭共振達門檻的標的。"""
    stock_ids, _ = get_universe(universe, symbols)
    fetcher = StockFetcher()
    indicators = TechnicalIndicators()
    hits: list[ResonanceHit] = []

    for stock_id in stock_ids:
        try:
            raw = fetcher.fetch(stock_id, period=period)
            if len(raw) < 2:
                continue
            enriched = indicators.compute(raw)
            fib = compute_fibonacci_retracement(enriched, lookback=FIB_SIGNAL_LOOKBACK)
            resonance = compute_bullish_resonance(enriched, fib)
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

    hits.sort(key=lambda h: (h.resonance.passed_count, h.symbol), reverse=True)
    return hits


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
) -> str:
    """將掃描結果格式化為 Telegram HTML 訊息。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if not hits:
        return (
            f"📊 <b>多頭共振掃描</b>（{now}）\n"
            f"股票池：{_escape_html(universe_label)}\n"
            f"門檻：≥ {min_passed}/6\n"
            f"\n今日無符合條件的標的。"
        )

    lines = [
        f"📊 <b>多頭共振掃描</b>（{now}）",
        f"股票池：{_escape_html(universe_label)}",
        f"門檻：≥ {min_passed}/6",
        f"符合 <b>{len(hits)}</b> 檔：",
        "",
    ]
    for hit in hits:
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
