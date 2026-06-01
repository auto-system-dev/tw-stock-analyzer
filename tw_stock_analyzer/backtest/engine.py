"""回測模擬引擎。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from tw_stock_analyzer.backtest.metrics import (
    DEFAULT_FEE_RATE,
    PerformanceMetrics,
    Trade,
    apply_round_trip_fee,
    buy_and_hold_return,
    compute_metrics,
)
from tw_stock_analyzer.backtest.strategies import composite_buy_signals, rsi_oversold_buy_signals
from tw_stock_analyzer.data.fetcher import StockFetcher
from tw_stock_analyzer.indicators.technical import TechnicalIndicators


@dataclass
class BacktestReport:
    """單一策略回測報告。"""

    symbol: str
    name: str
    period: str
    hold_days: int
    metrics: PerformanceMetrics
    trades: list[Trade]
    equity_curve: pd.Series


@dataclass
class ComparisonReport:
    """多策略比較報告。"""

    symbol: str
    name: str
    period: str
    hold_days: int
    buy_hold_return_pct: float
    strategies: list[BacktestReport]


class BacktestEngine:
    """回測主引擎。"""

    def __init__(
        self,
        hold_days: int = 5,
        fee_rate: float = DEFAULT_FEE_RATE,
    ):
        self.hold_days = hold_days
        self.fee_rate = fee_rate
        self.fetcher = StockFetcher()
        self.indicators = TechnicalIndicators()

    def run(
        self,
        symbol: str,
        period: str = "2y",
        strategy: str = "both",
    ) -> ComparisonReport:
        info = self.fetcher.fetch_info(symbol)
        raw = self.fetcher.fetch(symbol, period=period)
        df = self.indicators.compute(raw)
        bh_return = buy_and_hold_return(df, self.fee_rate)

        runners: list[tuple[str, Callable[[pd.DataFrame], pd.Series]]] = []
        if strategy in ("composite", "both"):
            runners.append(("綜合方向", composite_buy_signals))
        if strategy in ("rsi", "both"):
            runners.append(("RSI超賣", rsi_oversold_buy_signals))

        reports = []
        for name, signal_fn in runners:
            buy_mask = signal_fn(df)
            trades, equity = self._simulate(df, buy_mask)
            metrics = compute_metrics(name, trades, equity, bh_return)
            reports.append(
                BacktestReport(
                    symbol=info["symbol"],
                    name=info["name"],
                    period=period,
                    hold_days=self.hold_days,
                    metrics=metrics,
                    trades=trades,
                    equity_curve=equity,
                )
            )

        return ComparisonReport(
            symbol=info["symbol"],
            name=info["name"],
            period=period,
            hold_days=self.hold_days,
            buy_hold_return_pct=bh_return,
            strategies=reports,
        )

    def _simulate(
        self,
        df: pd.DataFrame,
        buy_mask: pd.Series,
    ) -> tuple[list[Trade], pd.Series]:
        """
        模擬交易：訊號日 T 收盤觸發，T+1 開盤買入，持有 hold_days 後於開盤賣出。
        持倉期間不重複進場。
        """
        trades: list[Trade] = []
        equity = pd.Series(index=df.index, dtype=float)
        capital = 1.0
        i = 1
        n = len(df)

        while i < n:
            equity.iloc[i] = capital
            signal_idx = i - 1
            if signal_idx >= 0 and buy_mask.iloc[signal_idx]:
                exit_idx = i + self.hold_days
                if exit_idx >= n:
                    break
                entry_price = float(df["open"].iloc[i])
                exit_price = float(df["open"].iloc[exit_idx])
                gross = exit_price / entry_price - 1
                net = apply_round_trip_fee(gross, self.fee_rate)
                capital *= 1 + net
                trades.append(
                    Trade(
                        entry_date=df.index[i],
                        exit_date=df.index[exit_idx],
                        entry_price=entry_price,
                        exit_price=exit_price,
                        return_pct=net,
                    )
                )
                for j in range(i, min(exit_idx + 1, n)):
                    equity.iloc[j] = capital
                i = exit_idx + 1
                continue
            i += 1

        equity = equity.ffill().fillna(1.0)
        return trades, equity
