"""互動式圖表：十字游標 + 頂部資料列（client-side hover）。"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

from tw_stock_analyzer.dashboard.charts import _build_chart_xaxis, build_combined_chart
from tw_stock_analyzer.dashboard.shareholding_chart import _load_over_1000_ratio_history
from tw_stock_analyzer.data.shareholding import align_over_1000_ratio_to_bars
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
        if "over_1000_ratio" in row.index:
            entry["over_1000_ratio"] = _num(row.get("over_1000_ratio"))
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
    chart_body = '<div id="chart"></div>'
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
  #chart-wrap { position: relative; }
  #fib-handle-layer {
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 6;
  }
  .fib-handle {
    position: absolute;
    width: 38px;
    height: 38px;
    margin-left: -19px;
    margin-top: -19px;
    border-radius: 50%;
    background: #fbbf24;
    border: 2px solid #ffffff;
    color: #1e293b;
    font-size: 11px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: grab;
    pointer-events: auto;
    touch-action: none;
    user-select: none;
    box-shadow: 0 2px 6px rgba(0,0,0,0.35);
  }
  .fib-handle.dragging {
    cursor: grabbing;
    z-index: 10;
    transform: scale(1.08);
  }"""
        fib_hint_html = (
            '<div id="fib-hint">手動模式：直接拖動黃色圓形把手（TradingView 式 HTML 拖曳 · 放開吸附 K 線/OHLC）</div>'
        )
        chart_body = (
            '<div id="chart-wrap"><div id="chart"></div>'
            '<div id="fib-handle-layer"></div></div>'
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
  #chart {{ width: 100%; height: 1000px; }}
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
{chart_body}
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

function nearestBarKey(x) {{
  const rounded = String(Math.round(Number(x)));
  if (dataMap[rounded]) return rounded;
  return xToKey(x);
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
    ${{d.over_1000_ratio != null ? `<span class="sep">|</span><span><span class="label">千張+</span>${{fmt(d.over_1000_ratio, 2)}}%</span>` : ''}}
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

function ohlcPriceBounds() {{
  let ymin = Infinity;
  let ymax = -Infinity;
  for (const d of Object.values(dataMap)) {{
    if (d.low != null) ymin = Math.min(ymin, d.low);
    if (d.high != null) ymax = Math.max(ymax, d.high);
  }}
  if (!Number.isFinite(ymin) || !Number.isFinite(ymax)) return null;
  const span = ymax - ymin;
  const padBelow = Math.max(span * 0.12, 30);
  const padAbove = Math.max(span * 0.45, 80);
  return {{ ymin, ymax, floor: ymin - padBelow, ceil: ymax + padAbove }};
}}

function clampAnchorPrice(price) {{
  const bounds = ohlcPriceBounds();
  if (!bounds) return Math.round(price * 100) / 100;
  const clamped = Math.max(bounds.floor, Math.min(bounds.ceil, price));
  return Math.round(clamped * 100) / 100;
}}

function computePriceYRange(levels) {{
  const bounds = ohlcPriceBounds();
  if (!bounds) return null;
  let ymin = bounds.ymin;
  let ymax = bounds.ymax;
  if (levels) {{
    for (const level of levels) {{
      if (level.price >= bounds.floor && level.price <= bounds.ceil) {{
        ymin = Math.min(ymin, level.price);
        ymax = Math.max(ymax, level.price);
      }}
    }}
  }}
  ymin = Math.max(ymin, bounds.floor);
  ymax = Math.min(ymax, bounds.ceil);
  const pad = Math.max((ymax - ymin) * 0.06, 20);
  return [ymin - pad, ymax + pad];
}}

function refreshLockedYRange(levels) {{
  const next = computePriceYRange(levels);
  if (!next) return;
  lockedYRange = next;
}}

let lastCrosshairPointer = null;

function pointerToPaper(relX, relY) {{
  const fl = gd._fullLayout;
  if (!fl?.xaxis || !fl?.yaxis) return null;
  const xax = fl.xaxis;
  const yax = fl.yaxis;
  const cx = Math.max(xax._offset, Math.min(xax._offset + xax._length, relX));
  const cy = Math.max(yax._offset, Math.min(yax._offset + yax._length, relY));
  const xPaper = xax.domain[0] + ((cx - xax._offset) / xax._length) * (xax.domain[1] - xax.domain[0]);
  const yPaper = yax.domain[0] + ((cy - yax._offset) / yax._length) * (yax.domain[1] - yax.domain[0]);
  return {{ cx, cy, xPaper, yPaper, xax, yax }};
}}

function getCrosshairShapes() {{
  if (!lastCrosshairPointer || suppressCrosshair || draggingAnchorId) return [];
  const paper = pointerToPaper(lastCrosshairPointer.relX, lastCrosshairPointer.relY);
  if (!paper) return [];
  const {{ xPaper, yPaper, xax, yax }} = paper;
  return [
    {{
      type: 'line',
      xref: 'paper',
      yref: 'paper',
      x0: xPaper,
      x1: xPaper,
      y0: yax.domain[0],
      y1: yax.domain[1],
      line: crosshairLine,
      layer: 'above',
    }},
    {{
      type: 'line',
      xref: 'paper',
      yref: 'paper',
      x0: xax.domain[0],
      x1: xax.domain[1],
      y0: yPaper,
      y1: yPaper,
      line: crosshairLine,
      layer: 'above',
    }},
  ];
}}

function applyLayoutPatch(patch) {{
  if (lockedYRange) {{
    patch['yaxis.autorange'] = false;
    patch['yaxis.range'] = lockedYRange;
  }}
  const baseShapes = patch.shapes !== undefined ? patch.shapes : activeShapes();
  patch.shapes = baseShapes.concat(getCrosshairShapes());
  return Plotly.relayout(gd, patch);
}}

function updateCrosshairFromPointer(relX, relY, source) {{
  lastCrosshairPointer = {{ relX, relY }};
  if (hasFibManual && source) {{
    const bb = gd.getBoundingClientRect();
    const paper = pointerToPaper(relX, relY);
    const fl = gd._fullLayout;
    dbgLog('interactive_chart.js:updateCrosshairFromPointer', 'paper crosshair', {{
      runId: 'crosshair-fix3',
      source,
      relX,
      relY,
      xPaper: paper?.xPaper,
      yPaper: paper?.yPaper,
      screenPx: paper ? bb.left + paper.cx : null,
      screenPy: paper ? bb.top + paper.cy : null,
    }}, 'H10,H11');
  }}
  return applyLayoutPatch({{}});
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
  lastCrosshairPointer = null;
  applyLayoutPatch({{ shapes }});
}}

function clearCrosshair() {{
  lastCrosshairPointer = null;
  applyLayoutPatch({{ shapes: activeShapes() }});
}}

const gd = document.getElementById('chart');
const baseShapes = (figObj.layout.shapes || []).slice();
const baseAnnotations = (figObj.layout.annotations || []).slice();
let fibShapes = [];
let fibLevelAnnotations = [];
let fibConfig = null;
let draggingAnchorId = null;
let fibPreviewQueued = false;
let fibHandleLayer = null;
let chartWrap = null;
let suppressCrosshair = false;
let lockedYRange = null;
let hasFibManual = false;

const FIB_RET_COLORS = {{
  '0%': '#94a3b8',
  '23.6%': '#64748b',
  '38.2%': '#eab308',
  '50%': '#f59e0b',
  '61.8%': '#f97316',
  '78.6%': '#fb923c',
  '100%': '#94a3b8',
}};
const FIB_TREND_LINE = {{
  color: 'rgba(148,163,184,0.75)',
  width: 1,
  dash: 'dot',
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
const FIB_RET_RATIOS = [
  [0, '0%'], [0.236, '23.6%'], [0.382, '38.2%'], [0.5, '50%'],
  [0.618, '61.8%'], [0.786, '78.6%'], [1, '100%'],
];
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

function showPoint(x, source, yPrice) {{
  const key = nearestBarKey(x);
  if (!dataMap[key]) return;
  renderBar(dataMap[key]);
  const crossY = yPrice !== undefined && yPrice !== null ? yPrice : dataMap[key].close;
  updateCrosshair(x, crossY);
}}

function showPointAtPointer(evt, source) {{
  const bb = gd.getBoundingClientRect();
  const relX = evt.clientX - bb.left;
  const relY = evt.clientY - bb.top;
  const fl = gd._fullLayout;
  if (!fl?.xaxis) return;
  const key = nearestBarKey(fl.xaxis.p2d(relX));
  if (!dataMap[key]) return;
  renderBar(dataMap[key]);
  updateCrosshairFromPointer(relX, relY, source);
}}

gd.on('plotly_hover', (event) => {{
  if (suppressCrosshair || draggingAnchorId) return;
  if (hasFibManual) return;
  if (!event.points || !event.points.length) return;
  showPoint(event.points[0].x, 'plotly_hover');
}});

gd.on('plotly_click', (event) => {{
  if (!event.points?.length || draggingAnchorId) return;
  showPoint(event.points[0].x, 'plotly_click');
}});

gd.on('plotly_unhover', () => {{
  if (suppressCrosshair || draggingAnchorId) return;
  if (hasFibManual) return;
  clearCrosshair();
  renderBar(dataMap[defaultKey]);
}});

function clampPointerToPricePanel(pointerPx, pointerPy) {{
  const yax = gd._fullLayout?.yaxis;
  if (!yax) return {{ pointerPx, pointerPy }};
  return {{
    pointerPx,
    pointerPy: Math.max(yax._offset, Math.min(yax._offset + yax._length, pointerPy)),
  }};
}}

function getPlotCoords(evt, clampY) {{
  const bb = gd.getBoundingClientRect();
  const fl = gd._fullLayout;
  if (!fl || !fl.xaxis || !fl.yaxis) return {{ x: 0, y: 0, pointerPx: 0, pointerPy: 0 }};
  let pointerPx = evt.clientX - bb.left;
  let pointerPy = evt.clientY - bb.top;
  if (clampY) {{
    const clamped = clampPointerToPricePanel(pointerPx, pointerPy);
    pointerPx = clamped.pointerPx;
    pointerPy = clamped.pointerPy;
  }}
  return {{
    x: fl.xaxis.p2d(pointerPx),
    y: fl.yaxis.p2d(pointerPy),
    pointerPx,
    pointerPy,
  }};
}}

function isInPricePanel(evt) {{
  const bb = gd.getBoundingClientRect();
  const yax = gd._fullLayout?.yaxis;
  if (!yax) return false;
  const yPx = evt.clientY - bb.top;
  return yPx >= yax._offset && yPx <= yax._offset + yax._length;
}}

function nearestBar(x) {{
  let bestBar = fibConfig.bars[0];
  let bestDist = Infinity;
  for (const bar of fibConfig.bars) {{
    const dist = Math.abs(bar.x - x);
    if (dist < bestDist) {{
      bestDist = dist;
      bestBar = bar;
    }}
  }}
  return bestBar;
}}

function magnetAnchorPrice(rawY, bar) {{
  const yax = gd._fullLayout?.yaxis;
  const candidates = [bar.open, bar.high, bar.low, bar.close].filter(
    (p) => p !== null && p !== undefined && Number.isFinite(p),
  );
  if (!yax || !candidates.length) return clampAnchorPrice(rawY);
  const rawPx = yax.d2p(rawY);
  let bestPrice = rawY;
  let bestPx = 12;
  for (const price of candidates) {{
    const pxDist = Math.abs(rawPx - yax.d2p(price));
    if (pxDist < bestPx) {{
      bestPx = pxDist;
      bestPrice = price;
    }}
  }}
  return clampAnchorPrice(bestPrice);
}}

function snapAnchor(x, y, finalize) {{
  const bar = nearestBar(x);
  const maxX = fibConfig.bars.length - 1;
  if (!finalize) {{
    return {{
      barIndex: Math.max(0, Math.min(maxX, x)),
      price: magnetAnchorPrice(y, bar),
    }};
  }}
  return {{
    barIndex: bar.index,
    price: magnetAnchorPrice(y, bar),
  }};
}}

function clampLayerPx(left, top) {{
  const xax = gd._fullLayout?.xaxis;
  const yax = gd._fullLayout?.yaxis;
  if (!xax || !yax) return {{ left, top }};
  return {{
    left: Math.max(xax._offset, Math.min(xax._offset + xax._length, left)),
    top: Math.max(yax._offset, Math.min(yax._offset + yax._length, top)),
  }};
}}

function anchorToLayerPx(anchor) {{
  const xax = gd._fullLayout.xaxis;
  const yax = gd._fullLayout.yaxis;
  return {{
    left: xax._offset + xax.d2p(anchor.barIndex),
    top: yax._offset + yax.d2p(anchor.price),
  }};
}}

function layerPxToAnchor(left, top, finalize) {{
  const xax = gd._fullLayout.xaxis;
  const yax = gd._fullLayout.yaxis;
  return snapAnchor(xax.p2d(left), yax.p2d(top), finalize);
}}

function scheduleFibPreview() {{
  if (fibPreviewQueued) return;
  fibPreviewQueued = true;
  requestAnimationFrame(() => {{
    fibPreviewQueued = false;
    renderFibOverlay();
  }});
}}

function renderFibHandles() {{
  if (!fibHandleLayer || !fibConfig) return;
  fibHandleLayer.innerHTML = '';
  for (const anchor of fibConfig.anchors) {{
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'fib-handle';
    btn.textContent = anchor.label;
    btn.dataset.anchorId = anchor.id;
    const pos = anchorToLayerPx(anchor);
    btn.style.left = `${{pos.left}}px`;
    btn.style.top = `${{pos.top}}px`;
    btn.addEventListener('pointerdown', (evt) => onHandlePointerDown(evt, anchor.id));
    fibHandleLayer.appendChild(btn);
  }}
}}

function onHandlePointerDown(evt, anchorId) {{
  if (!fibConfig || !chartWrap) return;
  evt.preventDefault();
  evt.stopPropagation();
  const anchor = fibConfig.anchors.find((a) => a.id === anchorId);
  const btn = evt.currentTarget;
  if (!anchor || !btn) return;
  draggingAnchorId = anchorId;
  suppressCrosshair = true;
  clearCrosshair();
  btn.classList.add('dragging');
  const wrapRect = chartWrap.getBoundingClientRect();
  const startLeft = parseFloat(btn.style.left) || 0;
  const startTop = parseFloat(btn.style.top) || 0;
  const grabDx = evt.clientX - wrapRect.left - startLeft;
  const grabDy = evt.clientY - wrapRect.top - startTop;

  function onMove(ev) {{
    let left = ev.clientX - wrapRect.left - grabDx;
    let top = ev.clientY - wrapRect.top - grabDy;
    ({{ left, top }} = clampLayerPx(left, top));
    btn.style.left = `${{left}}px`;
    btn.style.top = `${{top}}px`;
    const snapped = layerPxToAnchor(left, top, false);
    anchor.barIndex = snapped.barIndex;
    anchor.price = snapped.price;
    scheduleFibPreview();
  }}

  function onUp(ev) {{
    let left = parseFloat(btn.style.left) || 0;
    let top = parseFloat(btn.style.top) || 0;
    if (ev) {{
      left = ev.clientX - wrapRect.left - grabDx;
      top = ev.clientY - wrapRect.top - grabDy;
      ({{ left, top }} = clampLayerPx(left, top));
    }}
    const snapped = layerPxToAnchor(left, top, true);
    anchor.barIndex = snapped.barIndex;
    anchor.price = snapped.price;
    draggingAnchorId = null;
    suppressCrosshair = false;
    btn.classList.remove('dragging');
    renderFibOverlay();
    renderFibHandles();
    dbgLog('interactive_chart.js:handle-pointerup', 'html handle drag done', {{
      runId: 'html-handle',
      anchorId,
      after: snapped,
    }}, 'H17');
    window.removeEventListener('pointermove', onMove);
    window.removeEventListener('pointerup', onUp);
    window.removeEventListener('pointercancel', onUp);
  }}

  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onUp);
  dbgLog('interactive_chart.js:handle-pointerdown', 'html handle drag start', {{
    runId: 'html-handle',
    anchorId,
  }}, 'H17');
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

function computeRetracementLevels() {{
  const low = fibConfig.anchors.find((a) => a.role === 'low');
  const high = fibConfig.anchors.find((a) => a.role === 'high');
  if (!low || !high) return null;
  const price0 = low.price;
  const price1 = high.price;
  return FIB_RET_RATIOS.map(([ratio, label]) => ({{
    label,
    price: price0 + ratio * (price1 - price0),
  }}));
}}

function computeExtensionLevels() {{
  const a = fibConfig.anchors.find((x) => x.role === 'a');
  const b = fibConfig.anchors.find((x) => x.role === 'b');
  const c = fibConfig.anchors.find((x) => x.role === 'c');
  if (!a || !b || !c) return null;
  const impulse = b.price - a.price;
  return FIB_EXT_RATIOS.map(([ratio, label]) => ({{
    label,
    price: c.price + ratio * impulse,
  }}));
}}

function buildFibTrendShapes() {{
  const shapes = [];
  if (fibConfig.mode === 'extension') {{
    const a = fibConfig.anchors.find((x) => x.role === 'a');
    const b = fibConfig.anchors.find((x) => x.role === 'b');
    const c = fibConfig.anchors.find((x) => x.role === 'c');
    if (a && b) {{
      shapes.push({{
        type: 'line', xref: 'x', yref: 'y',
        x0: a.barIndex, y0: a.price, x1: b.barIndex, y1: b.price,
        line: FIB_TREND_LINE, layer: 'below',
      }});
    }}
    if (b && c) {{
      shapes.push({{
        type: 'line', xref: 'x', yref: 'y',
        x0: b.barIndex, y0: b.price, x1: c.barIndex, y1: c.price,
        line: FIB_TREND_LINE, layer: 'below',
      }});
    }}
    return shapes;
  }}
  const low = fibConfig.anchors.find((a) => a.role === 'low');
  const high = fibConfig.anchors.find((a) => a.role === 'high');
  if (low && high) {{
    shapes.push({{
      type: 'line', xref: 'x', yref: 'y',
      x0: low.barIndex, y0: low.price, x1: high.barIndex, y1: high.price,
      line: FIB_TREND_LINE, layer: 'below',
    }});
  }}
  return shapes;
}}

function fibLevelXRange() {{
  const anchorXs = fibConfig.anchors.map((a) => a.barIndex);
  const x0 = Math.min(...anchorXs);
  const x1 = fibConfig.bars[fibConfig.bars.length - 1].x;
  return {{ x0, x1 }};
}}

function renderFibOverlay() {{
  if (!fibConfig) return;
  const levels = fibConfig.mode === 'extension'
    ? computeExtensionLevels()
    : computeRetracementLevels();
  const colors = fibConfig.mode === 'extension' ? FIB_EXT_COLORS : FIB_RET_COLORS;
  const keyLevels = fibConfig.mode === 'extension' ? FIB_EXT_KEYS : FIB_RET_KEYS;
  const {{ x0, x1 }} = fibLevelXRange();
  fibShapes = buildFibTrendShapes();
  fibLevelAnnotations = [];
  dbgLog('interactive_chart.js:renderFibOverlay', 'levels computed', {{
    runId: 'ext-fix',
    mode: fibConfig.mode,
    levelCount: levels ? levels.length : 0,
    lockedYRange,
    anchors: fibConfig.anchors,
  }}, 'H8,H9');
  if (!levels) {{
    applyLayoutPatch({{
      shapes: activeShapes(),
      annotations: baseAnnotations.concat(fibLevelAnnotations),
    }});
    return;
  }}
  refreshLockedYRange(levels);
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

function onChartPointerMove(evt) {{
  if (!hasFibManual || suppressCrosshair || draggingAnchorId) return;
  if (!isInPricePanel(evt)) return;
  showPointAtPointer(evt, 'pointermove');
}}

function initFibInteractive() {{
  const el = document.getElementById('fib-config');
  if (!el) return;
  fibConfig = JSON.parse(el.textContent);
  if (!fibConfig.enabled) return;
  chartWrap = document.getElementById('chart-wrap');
  fibHandleLayer = document.getElementById('fib-handle-layer');
  for (const anchor of fibConfig.anchors) {{
    anchor.price = clampAnchorPrice(anchor.price);
  }}
  renderFibOverlay();
  renderFibHandles();
  gd.addEventListener('pointermove', onChartPointerMove, true);
  dbgLog('interactive_chart.js:initFibInteractive', 'html handles ready', {{
    runId: 'html-handle',
    anchorCount: fibConfig.anchors.length,
    xOffset: gd._fullLayout?.xaxis?._offset,
    yOffset: gd._fullLayout?.yaxis?._offset,
  }}, 'H17');
}}

window.addEventListener('resize', () => {{
  Plotly.Plots.resize(gd).then(() => {{
    if (hasFibManual && fibConfig) renderFibHandles();
  }});
}});
</script>
</body>
</html>"""


def render_interactive_chart(
    df: pd.DataFrame,
    title: str,
    *,
    symbol: str | None = None,
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
    chart_df = df
    over_1000_ratio = None
    if symbol:
        weekly = _load_over_1000_ratio_history(symbol)
        if weekly is not None and not weekly.empty:
            over_1000_ratio = align_over_1000_ratio_to_bars(df.index, weekly)
            chart_df = df.copy()
            chart_df["over_1000_ratio"] = over_1000_ratio
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
        chart_df,
        title,
        fib=fib,
        spec=chart_spec,
        fib_unit=fib_unit,
        fib_margin=fib_manual,
        over_1000_ratio=over_1000_ratio,
    )
    hover_map, default_key = build_hover_data(chart_df, chart_spec)
    fig_json = pio.to_json(fig)
    hover_json = json.dumps(hover_map, ensure_ascii=False)
    html = _chart_html(fig_json, hover_json, default_key, fib_config_json)
    has_share = over_1000_ratio is not None and over_1000_ratio.notna().any()
    iframe_h = 1080 if fib_manual else (1060 if has_share else 960)
    components.html(html, height=iframe_h, scrolling=True)
