"""互動式圖表：十字游標 + 頂部資料列（client-side hover）。"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

from tw_stock_analyzer.dashboard.charts import _build_chart_xaxis, build_combined_chart
from tw_stock_analyzer.indicators.chart_timeframe import (
    ChartTimeframeSpec,
    TIMEFRAME_SPECS,
    chart_hover_key,
    chart_volume_lots,
    format_chart_index,
)
from tw_stock_analyzer.indicators.fibonacci import FibOverlay, build_fib_anchor_config


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


def _chart_html(
    fig_json: str,
    hover_json: str,
    default_key: str,
    fib_config_json: str | None = None,
) -> str:
    fib_script_block = ""
    fib_hint_style = ""
    fib_hint_html = ""
    if fib_config_json is not None:
        fib_script_block = (
            f'<script id="fib-config" type="application/json">{fib_config_json}</script>'
        )
        fib_hint_style = """
  #fib-hint {
    font-size: 12px;
    color: #a78bfa;
    margin-bottom: 4px;
    padding: 0 2px;
  }"""
        fib_hint_html = (
            '<div id="fib-hint">手動模式：拖動圖上錨點（低/高 或 A/B/C）即時更新斐波那契線</div>'
        )
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
  }}{fib_hint_style}
</style>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
{fib_hint_html}
<div id="hover-bar"></div>
<div id="chart"></div>
<script id="fig-data" type="application/json">{fig_json}</script>
<script id="hover-data" type="application/json">{hover_json}</script>
{fib_script_block}
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

function activeShapes() {{
  return baseShapes.concat(fibShapes);
}}

function updateCrosshair(x, closePrice) {{
  const shapes = activeShapes();
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
  Plotly.relayout(gd, {{ shapes: activeShapes() }});
}}

const gd = document.getElementById('chart');
const baseShapes = (figObj.layout.shapes || []).slice();
const baseAnnotations = (figObj.layout.annotations || []).slice();
let fibShapes = [];
let fibLevelAnnotations = [];
let fibConfig = null;
let fibAnchorTraceIndex = null;
let draggingAnchorId = null;
let suppressCrosshair = false;

const FIB_RET_COLORS = {{
  '0%': '#94a3b8',
  '38.2%': '#eab308',
  '50%': '#f59e0b',
  '61.8%': '#f97316',
  '100%': '#94a3b8',
}};
const FIB_EXT_COLORS = {{
  '61.8%': '#a78bfa',
  '100%': '#8b5cf6',
  '127.2%': '#7c3aed',
  '161.8%': '#6d28d9',
  '200%': '#5b21b6',
  '261.8%': '#4c1d95',
}};
const FIB_RET_KEYS = new Set(['38.2%', '50%', '61.8%']);
const FIB_EXT_KEYS = new Set(['127.2%', '161.8%', '200%']);
const FIB_RET_RATIOS = [[0, '0%'], [0.382, '38.2%'], [0.5, '50%'], [0.618, '61.8%'], [1, '100%']];
const FIB_EXT_RATIOS = [[0.618, '61.8%'], [1, '100%'], [1.272, '127.2%'], [1.618, '161.8%'], [2, '200%'], [2.618, '261.8%']];
const ANCHOR_HIT_RADIUS = 14;

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
  if (suppressCrosshair || draggingAnchorId) return;
  if (!event.points || !event.points.length) return;
  showPoint(event.points[0].x);
}});

gd.on('plotly_click', (event) => {{
  if (draggingAnchorId) return;
  if (!event.points || !event.points.length) return;
  showPoint(event.points[0].x);
}});

gd.on('plotly_unhover', () => {{
  if (suppressCrosshair || draggingAnchorId) return;
  clearCrosshair();
  renderBar(dataMap[defaultKey]);
}});

function getPlotCoords(evt) {{
  const bb = gd.getBoundingClientRect();
  const xPx = evt.clientX - bb.left;
  const yPx = evt.clientY - bb.top;
  const fl = gd._fullLayout;
  return {{
    x: fl.xaxis.p2d(xPx),
    y: fl.yaxis.p2d(yPx),
  }};
}}

function snapAnchor(x, y) {{
  let bestBar = fibConfig.bars[0];
  let bestDist = Infinity;
  for (const bar of fibConfig.bars) {{
    const dist = Math.abs(bar.x - x);
    if (dist < bestDist) {{
      bestDist = dist;
      bestBar = bar;
    }}
  }}
  const price = Math.abs(y - bestBar.high) <= Math.abs(y - bestBar.low)
    ? bestBar.high
    : bestBar.low;
  return {{ barIndex: bestBar.index, price }};
}}

function findAnchorAt(evt) {{
  if (!fibConfig) return null;
  const bb = gd.getBoundingClientRect();
  const fl = gd._fullLayout;
  for (const anchor of fibConfig.anchors) {{
    const xPx = fl.xaxis.d2p(anchor.barIndex);
    const yPx = fl.yaxis.d2p(anchor.price);
    const dx = evt.clientX - bb.left - xPx;
    const dy = evt.clientY - bb.top - yPx;
    if (Math.hypot(dx, dy) < ANCHOR_HIT_RADIUS) return anchor;
  }}
  return null;
}}

function computeRetracementLevels() {{
  const low = fibConfig.anchors.find((a) => a.role === 'low');
  const high = fibConfig.anchors.find((a) => a.role === 'high');
  if (!low || !high || high.price <= low.price) return null;
  const upTrend = low.barIndex < high.barIndex;
  const range = high.price - low.price;
  return FIB_RET_RATIOS.map(([ratio, label]) => ({{
    label,
    price: upTrend ? high.price - ratio * range : low.price + ratio * range,
  }}));
}}

function computeExtensionLevels() {{
  const a = fibConfig.anchors.find((x) => x.role === 'a');
  const b = fibConfig.anchors.find((x) => x.role === 'b');
  const c = fibConfig.anchors.find((x) => x.role === 'c');
  if (!a || !b || !c) return null;
  const upTrend = a.barIndex < b.barIndex;
  if (upTrend) {{
    if (b.price <= a.price || c.price >= b.price || c.price <= a.price) return null;
    const impulse = b.price - a.price;
    return FIB_EXT_RATIOS.map(([ratio, label]) => ({{
      label,
      price: c.price + ratio * impulse,
    }}));
  }}
  if (b.price >= a.price || c.price <= b.price || c.price >= a.price) return null;
  const impulse = a.price - b.price;
  return FIB_EXT_RATIOS.map(([ratio, label]) => ({{
    label,
    price: c.price - ratio * impulse,
  }}));
}}

function renderFibOverlay() {{
  if (!fibConfig) return;
  const levels = fibConfig.mode === 'extension'
    ? computeExtensionLevels()
    : computeRetracementLevels();
  const colors = fibConfig.mode === 'extension' ? FIB_EXT_COLORS : FIB_RET_COLORS;
  const keyLevels = fibConfig.mode === 'extension' ? FIB_EXT_KEYS : FIB_RET_KEYS;
  const x0 = fibConfig.bars[0].x;
  const x1 = fibConfig.bars[fibConfig.bars.length - 1].x;
  fibShapes = [];
  fibLevelAnnotations = [];
  if (!levels) {{
    Plotly.relayout(gd, {{
      shapes: activeShapes(),
      annotations: baseAnnotations.concat(fibLevelAnnotations),
    }});
    return;
  }}
  for (const level of levels) {{
    const color = colors[level.label] || '#eab308';
    const width = keyLevels.has(level.label) ? 1.8 : 1.0;
    const opacity = keyLevels.has(level.label) ? 0.9 : 0.65;
    fibShapes.push({{
      type: 'line',
      xref: 'x',
      yref: 'y',
      x0,
      x1,
      y0: level.price,
      y1: level.price,
      line: {{ color, width, dash: 'dash' }},
      opacity,
      layer: 'below',
    }});
    fibLevelAnnotations.push({{
      x: x1,
      y: level.price,
      text: `${{level.label}} ${{Math.round(level.price).toLocaleString('zh-TW')}}`,
      showarrow: false,
      xanchor: 'left',
      xshift: 6,
      font: {{ size: 10, color }},
      bgcolor: 'rgba(15,23,42,0.8)',
      bordercolor: color,
      borderwidth: 1,
      borderpad: 2,
    }});
  }}
  Plotly.relayout(gd, {{
    shapes: activeShapes(),
    annotations: baseAnnotations.concat(fibLevelAnnotations),
  }});
}}

function updateAnchorMarkers() {{
  if (fibAnchorTraceIndex === null || !fibConfig) return;
  Plotly.restyle(gd, {{
    x: [fibConfig.anchors.map((a) => a.barIndex)],
    y: [fibConfig.anchors.map((a) => a.price)],
    text: [fibConfig.anchors.map((a) => a.label)],
  }}, [fibAnchorTraceIndex]);
}}

function initFibInteractive() {{
  const el = document.getElementById('fib-config');
  if (!el) return;
  fibConfig = JSON.parse(el.textContent);
  if (!fibConfig.enabled) return;

  Plotly.addTraces(gd, [{{
    x: fibConfig.anchors.map((a) => a.barIndex),
    y: fibConfig.anchors.map((a) => a.price),
    mode: 'markers+text',
    text: fibConfig.anchors.map((a) => a.label),
    textposition: 'top center',
    textfont: {{ color: '#fbbf24', size: 11 }},
    marker: {{
      size: 13,
      color: '#fbbf24',
      symbol: 'circle',
      line: {{ color: '#ffffff', width: 2 }},
    }},
    name: '_fib_anchors',
    hoverinfo: 'skip',
    showlegend: false,
  }}]).then(() => {{
    fibAnchorTraceIndex = gd.data.length - 1;
    renderFibOverlay();
  }});

  gd.addEventListener('mousedown', (evt) => {{
    const anchor = findAnchorAt(evt);
    if (!anchor) return;
    draggingAnchorId = anchor.id;
    suppressCrosshair = true;
    clearCrosshair();
    evt.preventDefault();
    evt.stopPropagation();
  }});

  window.addEventListener('mousemove', (evt) => {{
    if (!draggingAnchorId || !fibConfig) return;
    const {{ x, y }} = getPlotCoords(evt);
    const snapped = snapAnchor(x, y);
    const anchor = fibConfig.anchors.find((a) => a.id === draggingAnchorId);
    if (!anchor) return;
    anchor.barIndex = snapped.barIndex;
    anchor.price = snapped.price;
    updateAnchorMarkers();
    renderFibOverlay();
  }});

  window.addEventListener('mouseup', () => {{
    draggingAnchorId = null;
    suppressCrosshair = false;
  }});
}}

initFibInteractive();

window.addEventListener('resize', () => Plotly.Plots.resize(gd));
</script>
</body>
</html>"""


def render_interactive_chart(
    df: pd.DataFrame,
    title: str,
    *,
    fib: FibOverlay | None = None,
    spec: ChartTimeframeSpec | None = None,
    fib_unit: str = "日",
    fib_chart_mode: str | None = None,
    fib_manual: bool = False,
    fib_source: FibOverlay | None = None,
) -> None:
    """渲染含頂部資料列的互動圖表。"""
    chart_spec = spec or TIMEFRAME_SPECS["日線"]
    xaxis = _build_chart_xaxis(df, chart_spec)
    fib_config_json: str | None = None
    if fib_manual and fib_source is not None and fib_chart_mode is not None:
        fib_config = build_fib_anchor_config(
            df,
            fib_source,
            xaxis.coords,
            mode=fib_chart_mode,
            is_ordinal=xaxis.is_ordinal,
        )
        fib_config_json = json.dumps(fib_config, ensure_ascii=False)

    fig = build_combined_chart(
        df,
        title,
        fib=fib,
        spec=chart_spec,
        fib_unit=fib_unit,
        fib_margin=fib_manual,
    )
    hover_map, default_key = build_hover_data(df, chart_spec)
    fig_json = pio.to_json(fig)
    hover_json = json.dumps(hover_map, ensure_ascii=False)
    html = _chart_html(fig_json, hover_json, default_key, fib_config_json)
    components.html(html, height=980 if fib_manual else 960, scrolling=True)
