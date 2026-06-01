"""回測績效指標計算。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PerformanceMetrics:
    """策略績效摘要。"""

    strategy_name: str
    total_return_pct: float
    annualized_return_pct: float
    win_rate_pct: float
    avg_trade_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    vs_buy_hold_pct: float  # 相對 Buy & Hold 的超額報酬（百分點）


@dataclass
class Trade:
    """單筆模擬交易。"""

    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    entry_price: float
    exit_price: float
    return_pct: float


TRADING_DAYS_PER_YEAR = 252
DEFAULT_FEE_RATE = 0.001425  # 台股現股單邊手續費約 0.1425%


def apply_round_trip_fee(gross_return: float, fee_rate: float = DEFAULT_FEE_RATE) -> float:
    """扣除買賣雙邊手續費後的淨報酬。"""
    return (1.0 + gross_return) * (1.0 - fee_rate) ** 2 - 1.0


def compute_metrics(
    strategy_name: str,
    trades: list[Trade],
    equity_curve: pd.Series,
    buy_hold_return_pct: float,
) -> PerformanceMetrics:
    """由交易列表與權益曲線計算績效。"""
    if len(trades) == 0:
        total_return = 0.0
        win_rate = 0.0
        avg_trade = 0.0
    else:
        returns = [t.return_pct for t in trades]
        total_return = (np.prod([1 + r for r in returns]) - 1) * 100
        win_rate = sum(1 for r in returns if r > 0) / len(returns) * 100
        avg_trade = float(np.mean(returns)) * 100

    days = max(len(equity_curve) - 1, 1)
    if len(equity_curve) > 1 and equity_curve.iloc[-1] > 0:
        compounded = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
        annualized = ((1 + compounded) ** (TRADING_DAYS_PER_YEAR / days) - 1) * 100
    else:
        annualized = 0.0

    max_dd = _max_drawdown_pct(equity_curve)
    vs_bh = total_return - buy_hold_return_pct

    return PerformanceMetrics(
        strategy_name=strategy_name,
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(annualized, 2),
        win_rate_pct=round(win_rate, 2),
        avg_trade_return_pct=round(avg_trade, 2),
        max_drawdown_pct=round(max_dd, 2),
        num_trades=len(trades),
        vs_buy_hold_pct=round(vs_bh, 2),
    )


def _max_drawdown_pct(equity_curve: pd.Series) -> float:
    if len(equity_curve) < 2:
        return 0.0
    peak = equity_curve.expanding().max()
    drawdown = (equity_curve - peak) / peak
    return float(drawdown.min() * 100)


def buy_and_hold_return(df: pd.DataFrame, fee_rate: float = DEFAULT_FEE_RATE) -> float:
    """買入持有總報酬（%）。"""
    if len(df) < 2:
        return 0.0
    entry = float(df["open"].iloc[0])
    exit_price = float(df["close"].iloc[-1])
    gross = exit_price / entry - 1
    net = apply_round_trip_fee(gross, fee_rate)
    return round(net * 100, 2)
