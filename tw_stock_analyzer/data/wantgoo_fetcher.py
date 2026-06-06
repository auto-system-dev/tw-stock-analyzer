"""玩股網分 K 資料（與技術分析圖相同來源）。"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
import requests

from tw_stock_analyzer.data.symbol_utils import to_stock_id

WANTGOO_BASE = "https://www.wantgoo.com"
TW_SESSION_OFFSET = "9h"

TIMEFRAME_TO_CANDLESTICK: dict[str, str] = {
    "1分": "minute",
    "5分": "five-minutes",
    "15分": "quarter-hour",
    "30分": "half-hour",
    "60分": "hour",
}

RESAMPLE_RULE: dict[str, str] = {
    "1分": "1min",
    "5分": "5min",
    "15分": "15min",
    "30分": "30min",
    "60分": "60min",
}


class WantGooFetcher:
    """擷取玩股網 investrue K 線（成交量為張，僅含一般交易）。"""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def _prime_session(self, stock_id: str) -> None:
        self._session.headers["Referer"] = f"{WANTGOO_BASE}/stock/{stock_id}/technical-chart"
        self._session.headers["Origin"] = WANTGOO_BASE
        self._session.get(
            f"{WANTGOO_BASE}/stock/{stock_id}/technical-chart",
            timeout=20,
        )

    def _get_json(self, path: str) -> list[dict[str, Any]]:
        resp = self._session.get(f"{WANTGOO_BASE}{path}", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"玩股網回傳格式異常：{type(data)}")
        return data

    def _chunk_before_ms(self, candlestick_type: str) -> int:
        now = pd.Timestamp.now(tz="Asia/Taipei")
        if candlestick_type == "minute":
            anchor = now.floor("min") - pd.Timedelta(minutes=15)
        elif candlestick_type in {"five-minutes", "quarter-hour"}:
            anchor = now.floor("h") - pd.Timedelta(hours=2)
        elif candlestick_type in {"half-hour", "hour"}:
            anchor = now.floor("h") - pd.Timedelta(hours=3)
        else:
            anchor = now.floor("D") - pd.Timedelta(days=5)
        return int(anchor.value // 1_000_000)

    def fetch_candlesticks(self, symbol: str, timeframe: str) -> pd.DataFrame:
        stock_id = to_stock_id(symbol)
        candlestick_type = TIMEFRAME_TO_CANDLESTICK[timeframe]
        self._prime_session(stock_id)

        live_path = f"/investrue/{stock_id.lower()}/{candlestick_type.replace('_', '-')}-candlesticks"
        hist_path = (
            f"/investrue/{stock_id.lower()}/historical-"
            f"{candlestick_type.replace('_', '-')}-candlesticks"
            f"?before={self._chunk_before_ms(candlestick_type)}"
        )

        rows: list[dict[str, Any]] = []
        try:
            rows.extend(self._get_json(hist_path))
        except Exception:
            pass
        try:
            live_rows = self._get_json(live_path)
            if rows:
                last_hist = max(r["time"] for r in rows)
                live_rows = [r for r in live_rows if r["time"] > last_hist]
            rows.extend(live_rows)
        except Exception:
            if not rows:
                raise

        if not rows:
            raise ValueError(f"玩股網無 {timeframe} 資料")

        rows.sort(key=lambda r: r["time"])
        index = pd.to_datetime([r["time"] for r in rows], unit="ms", utc=True).tz_convert(
            "Asia/Taipei"
        )
        # 玩股網 volume 為張；內部 OHLCV 仍以股數存放以利 chart_volume_lots 統一換算
        volume_shares = [float(r.get("volume", 0) or 0) * 1000 for r in rows]
        return pd.DataFrame(
            {
                "open": [float(r["open"]) for r in rows],
                "high": [float(r["high"]) for r in rows],
                "low": [float(r["low"]) for r in rows],
                "close": [float(r["close"]) for r in rows],
                "volume": volume_shares,
            },
            index=index,
        )


def resample_yfinance_intraday(df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """將 Yahoo 1 分 K 依台股盤中時段重採樣（備援路徑）。"""
    if timeframe == "1分":
        return df_1m.copy()

    rule = RESAMPLE_RULE[timeframe]
    ohlcv = df_1m[list(OHLCV_COLS)].copy()
    ohlcv.index = pd.to_datetime(ohlcv.index)
    if getattr(ohlcv.index, "tz", None) is not None:
        ohlcv.index = ohlcv.index.tz_convert("Asia/Taipei")

    resampled = (
        ohlcv.resample(rule, origin="start_day", offset=TW_SESSION_OFFSET)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["close"])
    )
    return resampled


OHLCV_COLS = ("open", "high", "low", "close", "volume")
