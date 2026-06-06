"""互動式圖表：十字游標 + 頂部資料列（client-side hover）。"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

from tw_stock_analyzer.dashboard.charts import build_combined_chart
from tw_stock_analyzer.indicators.chart_timeframe import (
    ChartTimeframeSpec,
    TIMEFRAME_SPECS,
    chart_hover_key,
    chart_volume_lots,
    format_chart_index,
)
from tw_stock_analyzer.indicators.fibonacci import FibonacciRetracement


def _num(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return float(value)


def build_hover_data(
    df: pd.DataFrame,
    spec: ChartTimeframeSpec,
) -> tuple[dict[str, dict[str, Any]], str]:
    """建立以日期為 key 的 hover 資料表。"""
    data_map: dict[str, dict[str, Any]] = {}
    prev_close: float | None = None

    for bar_index, (idx, row) in enumerate(df.iterrows()):
        key = chart_hover_key(bar_index, idx, spec)
        display_date = format_chart_index(idx, spec)
        close = float(row["close"])
        change = close - prev_close if prev_close is not None else 0.0
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        entry = {
            "date": display_date,
            "close": close,
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": int(chart_volume_lots(pd.Series([row["volume"]])).iloc[0]),
            "change": change,
            "change_pct": change_pct,
            "rsi": _num(row.get("rsi_14")),
            "macd": _num(row.get("macd")),
            "macd_signal": _num(row.get("macd_signal")),
            "macd_hist": _num(row.get("macd_hist")),
            "sma_fast": _num(row.get("sma_50")),
            "sma_slow": _num(row.get("sma_200")),
            "sma_fast_label": spec.sma_fast,
            "sma_slow_label": spec.sma_slow,
        }
        data_map[key] = entry
        if key != str(bar_index):
            data_map[str(bar_index)] = entry
        prev_close = close

    default_key = next(reversed(data_map))
    return data_map, default_key


def _chart_html(fig_json: str, hover_json: str, default_key: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    padding: 0;
    background: transparent;
    font-family: "Segoe UI", "Microsoft JhengHei", sans-serif;
  }}
  #hover-bar {{
    font-size: 13px;
    line-height: 1.5;
    padding: 10px 14px;
    margin-bottom: 6px;
    background: rgba(15, 23, 42, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.25);
    border-radius: 8px;
    color: #e2e8f0;
    overflow-x: auto;
    white-space: nowrap;
  }}
  #hover-bar .date {{ color: #94a3b8; margin-right: 10px; }}
  #hover-bar .price {{ font-weight: 700; font-size: 15px; margin-right: 8px; }}
  #hover-bar .up {{ color: #ef4444; }}
  #hover-bar .down {{ color: #22c55e; }}
  #hover-bar .flat {{ color: #94a3b8; }}
  #hover-bar .sep {{ color: #475569; margin: 0 8px; }}
  #hover-bar .label {{ color: #64748b; margin-right: 4px; }}
  #chart {{ width: 100%; height: 880px; }}
  .js-plotly-plot .hoverlayer {{
    display: none !important;
  }}
  @media (max-width: 768px) {{
    #chart {{ height: 62vh; min-height: 420px; max-height: 680px; }}
    #hover-bar {{
      font-size: 12px;
      padding: 8px 10px;
      white-space: normal;
      line-height: 1.65;
    }}
    #hover-bar .sep {{ display: none; }}
    #hover-bar .price {{ font-size: 14px; display: block; margin: 2px 0; }}
    .modebar {{ transform: scale(0.85); transform-origin: top right; }}
  }}
</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
<div id="hover-bar"></div>
<div id="chart"></div>
<script id="fig-data" type="application/json">{fig_json}</script>
<script id="hover-data" type="application/json">{hover_json}</script>
<script>
const figObj = JSON.parse(document.getElementById('fig-data').textContent);
const dataMap = JSON.parse(document.getElementById('hover-data').textContent);
const defaultKey = {json.dumps(default_key)};

function fmt(n, digits=2) {{
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return Number(n).toLocaleString('zh-TW', {{
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }});
}}

function fmtVol(n) {{
  if (n === null || n === undefined) return '—';
  return Math.round(n).toLocaleString('zh-TW');
}}

function xToKey(x) {{
  const raw = String(x);
  if (dataMap[raw]) return raw;
  const d = new Date(x);
  if (!Number.isNaN(d.getTime())) {{
    const ms = String(d.getTime());
    if (dataMap[ms]) return ms;
  }}
  return raw;
}}

function renderBar(d) {{
  if (!d) return;
  const chgCls = d.change > 0 ? 'up' : (d.change < 0 ? 'down' : 'flat');
  const sign = d.change > 0 ? '+' : '';
  const bar = document.getElementById('hover-bar');
  bar.innerHTML = `
    <span class="date">${{d.date}}</span>
    <span class="price ${{chgCls}}">${{fmt(d.close)}}</span>
    <span class="${{chgCls}}">${{sign}}${{fmt(d.change)}} (${{sign}}${{fmt(d.change_pct)}}%)</span>
    <span class="sep">|</span>
    <span><span class="label">開</span>${{fmt(d.open)}}</span>
    <span class="sep">|</span>
    <span><span class="label">高</span>${{fmt(d.high)}}</span>
    <span class="sep">|</span>
    <span><span class="label">低</span>${{fmt(d.low)}}</span>
    <span class="sep">|</span>
    <span><span class="label">量</span>${{fmtVol(d.volume)}} 張</span>
    <span class="sep">|</span>
    <span><span class="label">RSI</span>${{fmt(d.rsi, 1)}}</span>
    <span class="sep">|</span>
    <span><span class="label">MACD</span>${{fmt(d.macd, 4)}}</span>
    <span class="sep">|</span>
    <span><span class="label">DIF</span>${{fmt(d.macd, 4)}}</span>
    <span class="sep">|</span>
    <span><span class="label">OSC</span>${{fmt(d.macd_hist, 4)}}</span>
    <span class="sep">|</span>
    <span><span class="label">SMA${{d.sma_fast_label}}</span>${{fmt(d.sma_fast)}}</span>
    <span class="sep">|</span>
    <span><span class="label">SMA${{d.sma_slow_label}}</span>${{fmt(d.sma_slow)}}</span>
  `;
}}

const crosshairLine = {{
  color: 'rgba(148,163,184,0.55)',
  width: 0.8,
  dash: 'dash',
}};

function updateCrosshair(x, closePrice) {{
  const shapes = baseShapes.slice();
  shapes.push(
    {{
      type: 'line',
      xref: 'x',
      yref: 'paper',
      x0: x,
      x1: x,
      y0: 0,
      y1: 1,
      line: crosshairLine,
      layer: 'above',
    }}
  );
  if (closePrice !== null && closePrice !== undefined) {{
    shapes.push({{
      type: 'line',
      xref: 'paper',
      yref: 'y',
      x0: 0,
      x1: 1,
      y0: closePrice,
      y1: closePrice,
      line: crosshairLine,
      layer: 'above',
    }});
  }}
  Plotly.relayout(gd, {{ shapes }});
}}

function clearCrosshair() {{
  Plotly.relayout(gd, {{ shapes: baseShapes.slice() }});
}}

const gd = document.getElementById('chart');
const baseShapes = (figObj.layout.shapes || []).slice();

Plotly.newPlot(gd, figObj.data, figObj.layout, {{
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
}});

renderBar(dataMap[defaultKey]);

function showPoint(x) {{
  const key = xToKey(x);
  if (dataMap[key]) {{
    renderBar(dataMap[key]);
    updateCrosshair(x, dataMap[key].close);
  }}
}}

gd.on('plotly_hover', (event) => {{
  if (!event.points || !event.points.length) return;
  showPoint(event.points[0].x);
}});

gd.on('plotly_click', (event) => {{
  if (!event.points || !event.points.length) return;
  showPoint(event.points[0].x);
}});

gd.on('plotly_unhover', () => {{
  clearCrosshair();
  renderBar(dataMap[defaultKey]);
}});

window.addEventListener('resize', () => Plotly.Plots.resize(gd));
</script>
</body>
</html>"""


def render_interactive_chart(
    df: pd.DataFrame,
    title: str,
    *,
    fib: FibonacciRetracement | None = None,
    spec: ChartTimeframeSpec | None = None,
    fib_unit: str = "日",
) -> None:
    """渲染含頂部資料列的互動圖表。"""
    chart_spec = spec or TIMEFRAME_SPECS["日線"]
    fig = build_combined_chart(
        df,
        title,
        fib=fib,
        spec=chart_spec,
        fib_unit=fib_unit,
    )
    hover_map, default_key = build_hover_data(df, chart_spec)
    fig_json = pio.to_json(fig)
    hover_json = json.dumps(hover_map, ensure_ascii=False)
    html = _chart_html(fig_json, hover_json, default_key)
    components.html(html, height=960, scrolling=True)
