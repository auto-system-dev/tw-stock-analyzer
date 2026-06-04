"""Plotly 圖表繪製。"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tw_stock_analyzer.indicators.fibonacci import FibonacciRetracement

FIB_LINE_COLORS = {
    "0%": "#94a3b8",
    "38.2%": "#eab308",
    "50%": "#f59e0b",
    "61.8%": "#f97316",
    "100%": "#94a3b8",
}


def _add_fibonacci_lines(fig: go.Figure, df: pd.DataFrame, fib: FibonacciRetracement) -> None:
    x_start, x_end = df.index[0], df.index[-1]
    for level in fib.levels:
        color = FIB_LINE_COLORS.get(level.label, "#eab308")
        width = 1.8 if level.label in {"38.2%", "50%", "61.8%"} else 1.0
        fig.add_trace(
            go.Scatter(
                x=[x_start, x_end],
                y=[level.price, level.price],
                mode="lines",
                name=f"Fib {level.label} ({level.price:,.1f})",
                line=dict(color=color, width=width, dash="dash"),
                opacity=0.9 if level.label in {"38.2%", "50%", "61.8%"} else 0.65,
                hovertemplate=f"Fib {level.label}: %{{y:,.2f}}<extra></extra>",
            )
        )


def build_price_chart(
    df: pd.DataFrame,
    title: str,
    *,
    fib: FibonacciRetracement | None = None,
) -> go.Figure:
    """K 線 + 均線 + 布林通道，可選斐波那契回撤。"""
    fig = make_subplots(rows=1, cols=1, shared_xaxes=True)

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K線",
            increasing_line_color="#ef4444",
            decreasing_line_color="#22c55e",
        )
    )

    overlays = [
        ("sma_50", "SMA 50", "#f59e0b"),
        ("sma_200", "SMA 200", "#a855f7"),
        ("bb_upper", "布林上軌", "#64748b"),
        ("bb_middle", "布林中軌", "#94a3b8"),
        ("bb_lower", "布林下軌", "#64748b"),
    ]
    dash_styles = {"bb_upper": "dot", "bb_middle": "dash", "bb_lower": "dot"}
    for col, label, color in overlays:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col],
                name=label,
                line=dict(color=color, width=1.2, dash=dash_styles.get(col, "solid")),
                opacity=0.85 if col.startswith("bb_") else 1,
            )
        )

    if fib is not None:
        _add_fibonacci_lines(fig, df, fib)
        title = (
            f"{title} · Fib 回撤（{fib.trend} · {fib.lookback_days}日）"
        )

    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=420,
        margin=dict(l=40, r=20, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title="價格")
    return fig


def build_indicator_chart(df: pd.DataFrame) -> go.Figure:
    """RSI + MACD 子圖。"""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.45, 0.55],
        vertical_spacing=0.06,
        subplot_titles=("RSI (14)", "MACD"),
    )

    fig.add_trace(
        go.Scatter(x=df.index, y=df["rsi_14"], name="RSI", line=dict(color="#38bdf8")),
        row=1,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", opacity=0.5, row=1, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", opacity=0.5, row=1, col=1)
    fig.add_hrect(y0=30, y1=70, fillcolor="rgba(148,163,184,0.08)", line_width=0, row=1, col=1)

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["macd_hist"],
            name="MACD 柱",
            marker_color=[
                "#22c55e" if v >= 0 else "#ef4444" for v in df["macd_hist"]
            ],
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index, y=df["macd"], name="MACD", line=dict(color="#3b82f6", width=1.5)
        ),
        row=2,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["macd_signal"],
            name="Signal",
            line=dict(color="#f59e0b", width=1.2),
        ),
        row=2,
        col=1,
    )

    fig.update_layout(
        height=380,
        margin=dict(l=40, r=20, t=40, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
    )
    fig.update_yaxes(title_text="RSI", row=1, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=2, col=1)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    return fig


def build_volume_chart(df: pd.DataFrame) -> go.Figure:
    colors = [
        "#ef4444" if c >= o else "#22c55e"
        for c, o in zip(df["close"], df["open"])
    ]
    fig = go.Figure(
        go.Bar(x=df.index, y=df["volume"], marker_color=colors, name="成交量")
    )
    fig.update_layout(
        title="成交量",
        height=200,
        margin=dict(l=40, r=20, t=40, b=30),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
    )
    fig.update_yaxes(title="張")
    return fig
