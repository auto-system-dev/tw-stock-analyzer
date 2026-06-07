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

_DEBUG_LOG_PATH = "debug-f0896b.log"


def _debug_log(location: str, message: str, data: dict, hypothesis_id: str) -> None:
    # #region agent log
    import time
    from pathlib import Path

    entry = {
        "sessionId": "f0896b",
        "location": location,
        "message": message,
        "data": data,
        "hypothesisId": hypothesis_id,
        "timestamp": int(time.time() * 1000),
    }
    try:
        Path(_DEBUG_LOG_PATH).open("a", encoding="utf-8").write(
            json.dumps(entry, ensure_ascii=False) + "\n"
        )
    except OSError:
        pass
    # #endregion


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
  }
  #chart-wrap {
    position: relative;
  }
  #fib-anchor-layer {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 20;
    overflow: visible;
  }
  .fib-anchor-handle {
    position: absolute;
    width: 32px;
    height: 32px;
    margin: 0;
    padding: 0;
    border: 2px solid #ffffff;
    border-radius: 50%;
    background: #fbbf24;
    color: #1e293b;
    font-size: 11px;
    font-weight: 700;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: grab;
    pointer-events: auto;
    user-select: none;
    touch-action: none;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.35);
  }
  .fib-anchor-handle:active {
    cursor: grabbing;
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

function computePriceYRange() {{
  let ymin = Infinity;
  let ymax = -Infinity;
  for (const d of Object.values(dataMap)) {{
    if (d.low != null) ymin = Math.min(ymin, d.low);
    if (d.high != null) ymax = Math.max(ymax, d.high);
  }}
  if (!Number.isFinite(ymin) || !Number.isFinite(ymax)) return null;
  const pad = Math.max((ymax - ymin) * 0.06, 20);
  return [ymin - pad, ymax + pad];
}}

function applyLayoutPatch(patch) {{
  if (lockedYRange) {{
    patch['yaxis.autorange'] = false;
    patch['yaxis.range'] = lockedYRange;
  }}
  return Plotly.relayout(gd, patch);
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
  applyLayoutPatch({{ shapes }});
}}

function clearCrosshair() {{
  applyLayoutPatch({{ shapes: activeShapes() }});
}}

const gd = document.getElementById('chart');
const baseShapes = (figObj.layout.shapes || []).slice();
const baseAnnotations = (figObj.layout.annotations || []).slice();
let fibShapes = [];
let fibLevelAnnotations = [];
let fibConfig = null;
let fibAnchorLayer = null;
let draggingAnchorId = null;
let suppressCrosshair = false;
let lockedYRange = null;
let hasFibManual = false;

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
(function prepareFibManualLayout() {{
  const el = document.getElementById('fib-config');
  if (!el) return;
  try {{
    const cfg = JSON.parse(el.textContent);
    hasFibManual = Boolean(cfg.enabled);
    if (hasFibManual) figObj.layout.dragmode = false;
  }} catch (err) {{
    hasFibManual = false;
  }}
}})();

Plotly.newPlot(gd, figObj.data, figObj.layout, {{
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
}}).then(() => {{
  if (!hasFibManual) return;
  lockedYRange = computePriceYRange();
  const relayoutPatch = {{ dragmode: false }};
  if (lockedYRange) {{
    relayoutPatch['yaxis.autorange'] = false;
    relayoutPatch['yaxis.range'] = lockedYRange;
  }}
  return Plotly.relayout(gd, relayoutPatch).then(() => initFibInteractive());
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
  if (suppressCrosshair || draggingAnchorId || hasFibManual) return;
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
  const fl = gd._fullLayout;
  if (!fl || !fl.xaxis || !fl.yaxis) return {{ x: 0, y: 0 }};
  return {{
    x: fl.xaxis.p2d(evt.clientX - bb.left),
    y: fl.yaxis.p2d(evt.clientY - bb.top),
  }};
}}

function isInPricePanel(evt) {{
  const bb = gd.getBoundingClientRect();
  const yax = gd._fullLayout?.yaxis;
  if (!yax) return false;
  const yPx = evt.clientY - bb.top;
  return yPx >= yax._offset && yPx <= yax._offset + yax._length;
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

function ensureAnchorLayer() {{
  if (fibAnchorLayer) return fibAnchorLayer;
  let wrap = document.getElementById('chart-wrap');
  if (!wrap) {{
    wrap = document.createElement('div');
    wrap.id = 'chart-wrap';
    gd.parentNode.insertBefore(wrap, gd);
    wrap.appendChild(gd);
  }}
  fibAnchorLayer = document.createElement('div');
  fibAnchorLayer.id = 'fib-anchor-layer';
  wrap.appendChild(fibAnchorLayer);
  return fibAnchorLayer;
}}

function dbgLog(location, message, data, hypothesisId) {{
  // #region agent log
  fetch('http://127.0.0.1:7340/ingest/76d27155-2cf5-4d9d-8ebc-11308a635c83', {{
    method: 'POST',
    headers: {{ 'Content-Type': 'application/json', 'X-Debug-Session-Id': 'f0896b' }},
    body: JSON.stringify({{
      sessionId: 'f0896b',
      location,
      message,
      data,
      hypothesisId,
      timestamp: Date.now(),
    }}),
  }}).catch(() => {{}});
  // #endregion
}}

function renderAnchorHandles() {{
  const layer = ensureAnchorLayer();
  layer.innerHTML = '';
  if (!fibConfig || !gd._fullLayout) return;
  const fl = gd._fullLayout;
  const handleSize = 32;
  const half = handleSize / 2;
  const wrap = document.getElementById('chart-wrap');
  const gdRect = gd.getBoundingClientRect();
  const wrapRect = wrap ? wrap.getBoundingClientRect() : null;
  const layerRect = layer.getBoundingClientRect();
  const handlePositions = [];
  for (const anchor of fibConfig.anchors) {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fib-anchor-handle';
    btn.textContent = anchor.label;
    btn.dataset.id = anchor.id;
    const left = fl.xaxis.d2p(anchor.barIndex) - half;
    const top = fl.yaxis.d2p(anchor.price) - half;
    btn.style.left = `${{left}}px`;
    btn.style.top = `${{top}}px`;
    handlePositions.push({{
      id: anchor.id,
      barIndex: anchor.barIndex,
      price: anchor.price,
      left,
      top,
      d2pX: fl.xaxis.d2p(anchor.barIndex),
      d2pY: fl.yaxis.d2p(anchor.price),
    }});
    btn.addEventListener('mousedown', (evt) => {{
      draggingAnchorId = anchor.id;
      suppressCrosshair = true;
      clearCrosshair();
      evt.preventDefault();
      evt.stopPropagation();
    }});
    btn.addEventListener('touchstart', (evt) => {{
      if (!evt.touches || !evt.touches.length) return;
      draggingAnchorId = anchor.id;
      suppressCrosshair = true;
      clearCrosshair();
      evt.preventDefault();
    }}, {{ passive: false }});
    layer.appendChild(btn);
  }}
  dbgLog('interactive_chart.js:renderAnchorHandles', 'anchor positions computed', {{
    handlePositions,
    lockedYRange,
    xaxisRange: fl.xaxis.range,
    yaxisRange: fl.yaxis.range,
    xaxisOffset: fl.xaxis._offset,
    yaxisOffset: fl.yaxis._offset,
    xaxisLength: fl.xaxis._length,
    yaxisLength: fl.yaxis._length,
    gdSize: {{ w: gdRect.width, h: gdRect.height }},
    wrapSize: wrapRect ? {{ w: wrapRect.width, h: wrapRect.height }} : null,
    layerSize: {{ w: layerRect.width, h: layerRect.height }},
    gdWrapDelta: wrapRect ? {{
      left: gdRect.left - wrapRect.left,
      top: gdRect.top - wrapRect.top,
    }} : null,
  }}, 'H1,H3,H4,H5');
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
    applyLayoutPatch({{
      shapes: activeShapes(),
      annotations: baseAnnotations.concat(fibLevelAnnotations),
    }});
    return;
  }}
  for (const level of levels) {{
    const color = colors[level.label] || '#eab308';
    const width = keyLevels.has(level.label) ? 1.8 : 1.0;
    fibShapes.push({{
      type: 'line',
      xref: 'x',
      yref: 'y',
      x0,
      x1,
      y0: level.price,
      y1: level.price,
      line: {{ color, width, dash: 'dash' }},
      layer: 'below',
    }});
    fibLevelAnnotations.push({{
      x: x1,
      y: level.price,
      xref: 'x',
      yref: 'y',
      text: `${{level.label}} ${{Math.round(level.price).toLocaleString('zh-TW')}}`,
      showarrow: false,
      xanchor: 'left',
      xshift: 6,
      font: {{ size: 10, color }},
      bgcolor: 'rgba(15,23,42,0.8)',
      bordercolor: color,
      borderwidth: 1,
      borderpad: 2,
      cliponaxis: false,
    }});
  }}
  applyLayoutPatch({{
    shapes: activeShapes(),
    annotations: baseAnnotations.concat(fibLevelAnnotations),
  }});
}}

function onFibPointerMove(evt) {{
  if (draggingAnchorId && fibConfig) {{
    const {{ x, y }} = getPlotCoords(evt);
    const snapped = snapAnchor(x, y);
    const anchor = fibConfig.anchors.find((a) => a.id === draggingAnchorId);
    if (!anchor) return;
    anchor.barIndex = snapped.barIndex;
    anchor.price = snapped.price;
    renderAnchorHandles();
    renderFibOverlay();
    return;
  }}
  if (!hasFibManual || suppressCrosshair || !isInPricePanel(evt)) return;
  const {{ x }} = getPlotCoords(evt);
  showPoint(x);
}}

function onFibPointerUp() {{
  draggingAnchorId = null;
  suppressCrosshair = false;
}}

function initFibInteractive() {{
  const el = document.getElementById('fib-config');
  if (!el) return;
  fibConfig = JSON.parse(el.textContent);
  if (!fibConfig.enabled) return;

  requestAnimationFrame(() => {{
    requestAnimationFrame(() => {{
      renderAnchorHandles();
      renderFibOverlay();
    }});
  }});

  gd.addEventListener('mousemove', onFibPointerMove);
  window.addEventListener('mousemove', onFibPointerMove);
  window.addEventListener('mouseup', onFibPointerUp);
  window.addEventListener('touchmove', (evt) => {{
    if (!evt.touches || !evt.touches.length) return;
    onFibPointerMove(evt.touches[0]);
  }}, {{ passive: false }});
  window.addEventListener('touchend', onFibPointerUp);
}}

window.addEventListener('resize', () => {{
  Plotly.Plots.resize(gd);
  if (fibConfig && fibConfig.enabled) renderAnchorHandles();
}});
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
        _debug_log(
            "interactive_chart.py:render_interactive_chart",
            "server fib anchor config",
            {
                "mode": fib_chart_mode,
                "anchors": fib_config.get("anchors"),
                "barCount": len(fib_config.get("bars", [])),
                "isOrdinal": xaxis.is_ordinal,
                "fibSource": (
                    {
                        "swing_high": getattr(fib_source, "swing_high", None),
                        "swing_low": getattr(fib_source, "swing_low", None),
                    }
                    if hasattr(fib_source, "swing_high")
                    else {
                        "point_a": getattr(fib_source, "point_a", None),
                        "point_b": getattr(fib_source, "point_b", None),
                        "point_c": getattr(fib_source, "point_c", None),
                    }
                ),
            },
            "H2",
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
