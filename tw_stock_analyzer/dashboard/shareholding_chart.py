"""持股 1000 張以上比例柱狀圖。"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from tw_stock_analyzer.data.shareholding import ShareholdingProvider


@st.cache_data(ttl=3600, show_spinner=False)
def _load_over_1000_ratio_history(symbol: str) -> pd.DataFrame | None:
    """快取集保千張大戶比例（每週更新，快取 1 小時）。"""
    df = ShareholdingProvider(weeks=26).fetch_over_1000_ratio_history(symbol)
    if df is None or df.empty:
        return None
    return df.copy()


def render_over_1000_ratio_chart(symbol: str, *, chart_key: str) -> None:
    """持股 1000 張以上比例走勢圖。"""
    df = _load_over_1000_ratio_history(symbol)
    if df is None:
        st.caption("未取得集保戶股權分散資料，千張大戶比例圖暫無法顯示。")
        return

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    latest = df["date"].max()
    st.caption(
        f"集保戶股權分散表 · 近 {len(df)} 週 · 截至 {latest.strftime('%Y-%m-%d')} · 每週更新"
    )
    st.plotly_chart(
        build_over_1000_ratio_chart(df),
        width="stretch",
        key=chart_key,
    )


def build_over_1000_ratio_chart(df: pd.DataFrame) -> go.Figure:
    """千張大戶持股比例走勢（紅漲綠跌柱狀圖）。"""
    ratios = df["ratio"].astype(float)
    prev = ratios.shift(1)
    colors = [
        "#ef4444" if (pd.isna(p) or r >= p) else "#22c55e"
        for r, p in zip(ratios, prev)
    ]
    latest = float(ratios.iloc[-1])
    x_labels = df["date"].dt.strftime("%m/%d").tolist()

    n = len(df)
    step = max(1, n // 6)
    tick_idxs = list(range(0, n, step))
    if tick_idxs[-1] != n - 1:
        tick_idxs.append(n - 1)

    y_min = float(ratios.min())
    y_max = float(ratios.max())
    pad = max((y_max - y_min) * 0.12, 0.5)
    y0 = max(0, y_min - pad)
    y1 = y_max + pad

    fig = go.Figure(
        go.Bar(
            x=list(range(n)),
            y=ratios,
            marker=dict(color=colors, line=dict(width=0)),
            width=0.55,
            hovertemplate="%{customdata}<br>比例 %{y:.2f}%<extra></extra>",
            customdata=df["date"].dt.strftime("%Y-%m-%d").tolist(),
            showlegend=False,
        )
    )
    fig.update_layout(
        title=dict(
            text=f"持股1000張以上比例  <b>{latest:.2f}</b>",
            x=0.01,
            xanchor="left",
            font=dict(size=14),
        ),
        height=300,
        margin=dict(l=12, r=48, t=48, b=32),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        bargap=0.08,
    )
    fig.update_xaxes(
        tickvals=tick_idxs,
        ticktext=[x_labels[i] for i in tick_idxs],
        showgrid=False,
        zeroline=False,
    )
    fig.update_yaxes(
        side="right",
        range=[y0, y1],
        showgrid=True,
        gridcolor="rgba(255,255,255,0.08)",
        ticksuffix="%",
        tickformat=".0f",
    )
    return fig
