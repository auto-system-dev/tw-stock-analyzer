"""Plotly 圖表繪製。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from tw_stock_analyzer.indicators.fibonacci import FibonacciRetracement
from tw_stock_analyzer.indicators.chart_timeframe import (
    ChartTimeframeSpec,
    TIMEFRAME_SPECS,
    format_chart_index,
    uses_ordinal_x_axis,
)

@dataclass(frozen=True)
class ChartXAxis:
    coords: list
    is_ordinal: bool
    tick_vals: list[int] | None = None
    tick_text: list[str] | None = None


def _build_chart_xaxis(df: pd.DataFrame, chart_spec: ChartTimeframeSpec) -> ChartXAxis:
    """日/週/月線與分 K 用整數序數 X 軸，消除盤後與假日造成的視覺空洞。"""
    if not uses_ordinal_x_axis(chart_spec):
        return ChartXAxis(coords=df.index.tolist(), is_ordinal=False)
    n = len(df)
    step = max(1, n // 6)
    tick_idxs = list(range(0, n, step))
    if tick_idxs[-1] != n - 1:
        tick_idxs.append(n - 1)
    tick_text = [format_chart_index(df.index[i], chart_spec) for i in tick_idxs]
    return ChartXAxis(
        coords=list(range(n)),
        is_ordinal=True,
        tick_vals=tick_idxs,
        tick_text=tick_text,
    )


def _apply_ordinal_axis(fig: go.Figure, xaxis: ChartXAxis, *, n_rows: int = 4) -> None:
    if not xaxis.is_ordinal or not xaxis.tick_vals:
        return
    n = len(xaxis.coords)
    x_range = [-0.5, n - 0.5]
    for row in range(1, n_rows + 1):
        fig.update_xaxes(
            type="linear",
            tickmode="array",
            tickvals=xaxis.tick_vals,
            ticktext=xaxis.tick_text,
            range=x_range,
            autorange=False,
            fixedrange=True,
            row=row,
            col=1,
        )
    fig.update_layout(bargap=0, bargroupgap=0)
    fig.update_traces(width=1.0, selector=dict(type="bar"))


FIB_LINE_COLORS = {
    "0%": "#94a3b8",
    "38.2%": "#eab308",
    "50%": "#f59e0b",
    "61.8%": "#f97316",
    "100%": "#94a3b8",
}


def _add_fibonacci_levels(
    fig: go.Figure,
    df: pd.DataFrame,
    fib: FibonacciRetracement,
    x_coords: list,
    *,
    row: int = 1,
    col: int = 1,
    hover_info: str | None = "skip",
) -> None:
    """繪製 Fib 水平線；標籤放圖表右側，不佔用頂部圖例。"""
    x_start, x_end = x_coords[0], x_coords[-1]
    for level in fib.levels:
        color = FIB_LINE_COLORS.get(level.label, "#eab308")
        width = 1.8 if level.label in {"38.2%", "50%", "61.8%"} else 1.0
        trace_kwargs: dict = dict(
            x=[x_start, x_end],
            y=[level.price, level.price],
            mode="lines",
            line=dict(color=color, width=width, dash="dash"),
            opacity=0.9 if level.label in {"38.2%", "50%", "61.8%"} else 0.65,
            showlegend=False,
        )
        if hover_info == "skip":
            trace_kwargs["hoverinfo"] = "skip"
        else:
            trace_kwargs["hovertemplate"] = f"Fib {level.label}: %{{y:,.2f}}<extra></extra>"
        fig.add_trace(go.Scatter(**trace_kwargs), row=row, col=col)

        fig.add_annotation(
            x=x_end,
            y=level.price,
            text=f"{level.label} {level.price:,.0f}",
            showarrow=False,
            xanchor="left",
            xshift=6,
            font=dict(size=10, color=color),
            bgcolor="rgba(15,23,42,0.8)",
            bordercolor=color,
            borderwidth=1,
            borderpad=2,
            row=row,
            col=col,
        )


def _add_fibonacci_lines(
    fig: go.Figure,
    df: pd.DataFrame,
    fib: FibonacciRetracement,
    x_coords: list,
) -> None:
    _add_fibonacci_levels(fig, df, fib, x_coords, hover_info="hover")


def _add_hover_capture(
    fig: go.Figure,
    df: pd.DataFrame,
    x_coords: list,
    row: int,
    y_col: str,
) -> None:
    """透明 hover 捕捉點，確保各子圖能觸發 plotly_hover。"""
    if y_col not in df.columns:
        return
    fig.add_trace(
        go.Scatter(
            x=x_coords,
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
    x_coords: list,
    *,
    row: int = 1,
    col: int = 1,
    skip_hover: bool = False,
) -> None:
    hover = "skip" if skip_hover else None
    fig.add_trace(
        go.Candlestick(
            x=x_coords,
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
        is_bb = col_name.startswith("bb_")
        fig.add_trace(
            go.Scatter(
                x=x_coords,
                y=df[col_name],
                name=label,
                line=dict(color=color, width=1.2, dash=dash_styles.get(col_name, "solid")),
                opacity=0.85 if is_bb else 1,
                showlegend=not is_bb,
                hoverinfo=hover,
                connectgaps=False,
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
    xaxis = _build_chart_xaxis(df, chart_spec)
    x_coords = xaxis.coords
    fig = make_subplots(
        rows=4,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.48, 0.14, 0.19, 0.19],
        vertical_spacing=0.03,
        subplot_titles=(None, None, "RSI (14)", "MACD"),
    )

    _add_price_traces(fig, df, chart_spec, x_coords, row=1, skip_hover=True)

    if fib is not None:
        _add_fibonacci_levels(fig, df, fib, x_coords, row=1, col=1)

    vol_colors = [
        "#ef4444" if c >= o else "#22c55e" for c, o in zip(df["close"], df["open"])
    ]
    fig.add_trace(
        go.Bar(
            x=x_coords,
            y=df["volume"],
            name="成交量",
            marker=dict(color=vol_colors, line=dict(width=0)),
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=x_coords,
            y=df["rsi_14"],
            name="RSI",
            line=dict(color="#38bdf8"),
            hoverinfo="skip",
            showlegend=False,
            connectgaps=False,
        ),
        row=3,
        col=1,
    )
    fig.add_hline(y=70, line_dash="dot", line_color="#ef4444", opacity=0.5, row=3, col=1)
    fig.add_hline(y=30, line_dash="dot", line_color="#22c55e", opacity=0.5, row=3, col=1)

    fig.add_trace(
        go.Bar(
            x=x_coords,
            y=df["macd_hist"],
            name="MACD 柱",
            marker_color=["#22c55e" if v >= 0 else "#ef4444" for v in df["macd_hist"]],
            hoverinfo="skip",
            showlegend=False,
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_coords,
            y=df["macd"],
            name="MACD",
            line=dict(color="#3b82f6", width=1.5),
            hoverinfo="skip",
            showlegend=False,
            connectgaps=False,
        ),
        row=4,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=x_coords,
            y=df["macd_signal"],
            name="Signal",
            line=dict(color="#f59e0b", width=1.2),
            hoverinfo="skip",
            showlegend=False,
            connectgaps=False,
        ),
        row=4,
        col=1,
    )

    title = f"{title}（{chart_spec.label}）"
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left", font=dict(size=14)),
        xaxis_rangeslider_visible=False,
        height=880,
        margin=dict(l=40, r=88 if fib is not None else 20, t=90, b=28),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0,
            font=dict(size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
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
    _add_hover_capture(fig, df, x_coords, 1, "close")
    _add_hover_capture(fig, df, x_coords, 2, "volume")
    _add_hover_capture(fig, df, x_coords, 3, "rsi_14")
    _add_hover_capture(fig, df, x_coords, 4, "macd")
    _apply_ordinal_axis(fig, xaxis)
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
    xaxis = _build_chart_xaxis(df, chart_spec)
    x_coords = xaxis.coords
    fig = make_subplots(rows=1, cols=1, shared_xaxes=True)

    _add_price_traces(fig, df, chart_spec, x_coords)

    if fib is not None:
        _add_fibonacci_lines(fig, df, fib, x_coords)

    title = f"{title}（{chart_spec.label}）"
    fig.update_layout(
        title=title,
        xaxis_rangeslider_visible=False,
        height=420,
        margin=dict(l=40, r=88 if fib is not None else 20, t=56, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(255,255,255,0.08)", title="價格")
    _apply_ordinal_axis(fig, xaxis, n_rows=1)
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
