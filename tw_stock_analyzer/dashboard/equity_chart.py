"""回測權益曲線圖表。"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go


def build_equity_chart(
    curves: dict[str, pd.Series],
    buy_hold_return_pct: float,
) -> go.Figure:
    """多策略權益曲線比較。"""
    fig = go.Figure()
    colors = ["#3b82f6", "#22c55e", "#f59e0b", "#a855f7"]
    for i, (name, series) in enumerate(curves.items()):
        base = float(series.iloc[0]) if len(series) and series.iloc[0] else 1.0
        normalized = series / base if base else series
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=normalized,
                name=name,
                line=dict(color=colors[i % len(colors)], width=2),
            )
        )
    fig.update_layout(
        title=f"權益曲線（Buy & Hold 總報酬 {buy_hold_return_pct:+.2f}%）",
        height=360,
        margin=dict(l=40, r=20, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="淨值（起始=1）",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    return fig
