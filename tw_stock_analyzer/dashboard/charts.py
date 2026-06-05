"""Plotly 圖表繪製。"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tw_stock_analyzer.indicators.fibonacci import FibonacciRetracement
from tw_stock_analyzer.indicators.chart_timeframe import ChartTimeframeSpec, TIMEFRAME_SPECS

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


def _add_hover_capture(
    fig: go.Figure,
    df: pd.DataFrame,
    row: int,
    y_col: str,
) -> None:
    """透明 hover 捕捉點，確保各子圖能觸發 plotly_hover。"""
    if y_col not in df.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df[y_col],
            mode="markers",
            marker=dict(size=14, color="rgba(0,0,0,0)"),
            showlegend=False,
            hovertemplate="<extra></extra>",
            name=f"_hover_{row}",
        ),
        row=row,
        col=1,
    )


def _apply_crosshair(fig: go.Figure, *, n_rows: int = 4) -> None:
    """設定 hover 行為；十字虛線由 JS 繪製，hover 白框由 CSS 隱藏。"""
    # #region agent log
    import json, sys, time
    _payload = {"sessionId": "4e6749", "hypothesisId": "B", "location": "charts.py:_apply_crosshair", "message": "apply crosshair v2", "data": {"hoverlabel": "removed"}, "timestamp": int(time.time() * 1000), "runId": "deploy-fix"}
    print(json.dumps(_payload), file=sys.stderr)
    try:
        open("debug-4e6749.log", "a", encoding="utf-8").write(json.dumps(_payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion
    fig.update_layout(
        hovermode="x unified",
        hoverdistance=80,
        spikedistance=-1,
    )
    for row in range(1, n_rows + 1):
        fig.update_xaxes(showspikes=False, row=row, col=1)
        fig.update_yaxes(showspikes=False, row=row, col=1)


def _add_price_traces(
    fig: go.Figure,
    df: pd.DataFrame,
    chart_spec: ChartTimeframeSpec,
    *,
    row: int = 1,
    col: int = 1,
    skip_hover: bool = False,
) -> None:
    hover = "skip" if skip_hover else None
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
            hoverinfo=hover,
        ),
        row=row,
        col=col,
    )
    overlays = [
        ("sma_50", f"SMA {chart_spec.sma_fast}", "#f59e0b"),
        ("sma_200", f"SMA {chart_spec.sma_slow}", "#a855f7"),
        ("bb_upper", "布林上軌", "#64748b"),
        ("bb_middle", "布林中軌", "#94a3b8"),
        ("bb_lower", "布林下軌", "#64748b"),
    ]
    dash_styles = {"bb_upper": "dot", "bb_middle": "dash", "bb_lower": "dot"}
    for col_name, label, color in overlays:
        if col_name not in df.columns or df[col_name].isna().all():
            continue
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df[col_name],
                name=label,
                line=dict(color=color, width=1.2, dash=dash_styles.get(col_name, "solid")),
                opacity=0.85 if col_name.startswith("bb_") else 1,
                hoverinfo=hover,
            ),
            row=row,
            col=col,
        )


def build_combined_chart(
    df: pd.DataFrame,
    title: str,
    *,
    fib: FibonacciRetracement | None = None,
    spec: ChartTimeframeSpec | None = None,
    fib_unit: str = "日",
) -> go.Figure:
    """K 線 + 成交量 + RSI + MACD 合併圖（含十字游標）。"""
    chart_spec = spec or TIMEFRAME_SPECS["日線"]
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.48, 0.14, 0.19, 0.19],
        vertical_spacing=0.03,
        subplot_titles=(None, None, "RSI (14)", "MACD"),
    )

    _add_price_traces(fig, df, chart_spec, row=1, skip_hover=True)

    if fib is not None:
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
                    hoverinfo="skip",
                ),
                row=1,
                col=1,
            )
        title = f"{title} · Fib 回撤（{fib.trend} · {fib.lookback_days}{fib_unit}）"

    vol_colors = [
        "#ef4444" if c >= o else "#22c55e" for c, o in zip(df["close"], df["open"])
    ]
    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["volume"],
            name="成交量",
            marker_color=vol_colors,
            hoverinfo="skip",
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["rsi_14"],
            name="RSI",
            line=dict(color="#38bdf8"),
            hoverinfo="skip",
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", opacity=0.5, row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", opacity=0.5, row=3, col=1)

    fig.add_trace(
        go.Bar(
            x=df.index,
            y=df["macd_hist"],
            name="MACD 柱",
            marker_color=["#22c55e" if v >= 0 else "#ef4444" for v in df["macd_hist"]],
            hoverinfo="skip",
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["macd"],
            name="MACD",
            line=dict(color="#3b82f6", width=1.5),
            hoverinfo="skip",
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=df.index,
            y=df["macd_signal"],
            name="Signal",
            line=dict(color="#f59e0b", width=1.2),
            hoverinfo="skip",
        ),
        row=4,
        col=1,
    )

    title = f"{title}（{chart_spec.label}）"
    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=880,
        margin=dict(l=48, r=24, t=56, b=28),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_yaxes(title_text="價格", row=1, col=1)
    fig.update_yaxes(title_text="量", row=2, col=1)
    fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])
    fig.update_yaxes(title_text="MACD", row=4, col=1)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    for r in (1, 2, 3):
        fig.update_xaxes(showticklabels=False, row=r, col=1)
    _add_hover_capture(fig, df, 1, "close")
    _add_hover_capture(fig, df, 2, "volume")
    _add_hover_capture(fig, df, 3, "rsi_14")
    _add_hover_capture(fig, df, 4, "macd")
    _apply_crosshair(fig)
    return fig


def build_price_chart(
    df: pd.DataFrame,
    title: str,
    *,
    fib: FibonacciRetracement | None = None,
    spec: ChartTimeframeSpec | None = None,
    fib_unit: str = "日",
) -> go.Figure:
    """K 線 + 均線 + 布林通道，可選斐波那契回撤。"""
    chart_spec = spec or TIMEFRAME_SPECS["日線"]
    fig = make_subplots(rows=1, cols=1, shared_xaxes=True)

    _add_price_traces(fig, df, chart_spec)

    if fib is not None:
        _add_fibonacci_lines(fig, df, fib)
        title = (
            f"{title} · Fib 回撤（{fib.trend} · {fib.lookback_days}{fib_unit}）"
        )

    title = f"{title}（{chart_spec.label}）"
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
