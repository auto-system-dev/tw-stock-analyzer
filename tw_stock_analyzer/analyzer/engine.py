"""整合資料擷取、技術分析與預測。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from tw_stock_analyzer.analyzer.scoring import PotentialScore, compute_potential_score
from tw_stock_analyzer.data.fetcher import StockFetcher
from tw_stock_analyzer.data.market_context import MarketContextProvider
from tw_stock_analyzer.data.models import MarketContext
from tw_stock_analyzer.indicators.fibonacci import (
    FIB_SIGNAL_LOOKBACK,
    compute_fibonacci_retracement,
)
from tw_stock_analyzer.indicators.technical import TechnicalIndicators
from tw_stock_analyzer.predictor.model import PredictionResult, PricePredictor
from tw_stock_analyzer.predictor.signals import (
    aggregate_direction,
    rule_signals_from_row,
    with_fibonacci_signal,
)


@dataclass
class AnalysisReport:
    """完整分析報告。"""

    symbol: str
    name: str
    analyzed_at: datetime
    period: str
    latest_date: datetime
    ohlcv: pd.DataFrame
    prediction: PredictionResult
    market_context: MarketContext
    potential_score: PotentialScore
    summary: str


class StockAnalyzer:
    """台股分析主引擎。"""

    def __init__(self, horizon_days: int = 5):
        self.fetcher = StockFetcher()
        self.indicators = TechnicalIndicators()
        self.predictor = PricePredictor(horizon_days=horizon_days)
        self.market = MarketContextProvider(institutional_days=min(horizon_days, 10))

    def analyze(
        self,
        symbol: str,
        period: str = "2y",
    ) -> AnalysisReport:
        info = self.fetcher.fetch_info(symbol)
        raw = self.fetcher.fetch(symbol, period=period)
        enriched = self.indicators.compute(raw)
        fib = compute_fibonacci_retracement(enriched, lookback=FIB_SIGNAL_LOOKBACK)
        prediction = self.predictor.predict(enriched)
        market_context = self.market.fetch(symbol, info["name"])
        latest = enriched.iloc[-1]
        signals = with_fibonacci_signal(
            rule_signals_from_row(latest),
            float(latest["close"]),
            fib,
        )
        prediction.signals = signals
        prediction.direction = aggregate_direction(
            prediction.predicted_change_pct / 100,
            signals,
            use_ml=True,
        )
        potential_score = compute_potential_score(
            latest,
            signals,
            market_context,
            prediction,
            use_ml=True,
        )

        summary = self._build_summary(info["name"], prediction, market_context, potential_score)
        return AnalysisReport(
            symbol=info["symbol"],
            name=info["name"],
            analyzed_at=datetime.now(),
            period=period,
            latest_date=enriched.index[-1].to_pydatetime(),
            ohlcv=enriched,
            prediction=prediction,
            market_context=market_context,
            potential_score=potential_score,
            summary=summary,
        )

    def _build_summary(
        self,
        name: str,
        pred: PredictionResult,
        ctx: MarketContext,
        score: PotentialScore,
    ) -> str:
        change_word = "上漲" if pred.predicted_change_pct >= 0 else "下跌"
        theme_part = f"偵測題材：{ctx.themes_summary()}。"
        chip_part = ""
        if ctx.institutional:
            i = ctx.institutional
            chip_part = (
                f"近{i.period_days}日法人淨買超 {i.total_net:,.0f} 張"
                f"（外資 {i.foreign_net:,.0f}、投信 {i.trust_net:,.0f}）。"
            )
        top_reasons = "；".join(score.reasons[:3]) if score.reasons else "—"
        return (
            f"{name} 目前收盤 {pred.current_price:.2f} 元，"
            f"模型預估 {pred.horizon_days} 日後{change_word} "
            f"{abs(pred.predicted_change_pct):.2f}%（目標約 {pred.predicted_price:.2f} 元），"
            f"綜合判斷：{pred.direction}。"
            f"潛力評分 {score.total}/100（{score.grade} 級），"
            f"持有類型：{score.holding_type}（{score.holding_period}）。"
            f"重點：{top_reasons}。"
            f"{chip_part}{theme_part}"
            f"此結果僅供研究參考，不構成投資建議。"
        )
