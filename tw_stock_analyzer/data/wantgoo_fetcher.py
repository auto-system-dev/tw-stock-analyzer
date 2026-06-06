"""玩股網分 K 資料（與技術分析圖相同來源）。"""

from __future__ import annotations

import time
from typing import Any

import pandas as pd
from curl_cffi import requests

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
        self._session = requests.Session(impersonate="chrome136")
        self._session.headers.update(
            {
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
        url = f"{WANTGOO_BASE}{path}"
        resp = self._session.get(url, timeout=30)
        # #region agent log
        import json
        from pathlib import Path

        _log = Path(__file__).resolve().parents[2] / "debug-938789.log"
        with _log.open("a", encoding="utf-8") as _f:
            _f.write(
                json.dumps(
                    {
                        "sessionId": "938789",
                        "hypothesisId": "A,B,C",
                        "location": "wantgoo_fetcher.py:_get_json",
                        "message": "wantgoo http response",
                        "data": {
                            "path": path,
                            "status": resp.status_code,
                            "ok": resp.ok,
                            "body_prefix": (resp.text or "")[:120],
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
        # #endregion
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"玩股網回傳格式異常：{type(data)}")
        return data

    def _historical_before_candidates(self, candlestick_type: str) -> list[int]:
        """玩股網 before 偏移（對齊 JS：-3h startOf hour，少量備援避免觸發 WAF）。"""
        now = pd.Timestamp.now(tz="Asia/Taipei")
        if candlestick_type == "minute":
            offsets = [15, 20, 25]
            anchors = [now.floor("min") - pd.Timedelta(minutes=m) for m in offsets]
        elif candlestick_type in {"five-minutes", "quarter-hour"}:
            offsets = [2, 3, 4]
            anchors = [now.floor("h") - pd.Timedelta(hours=h) for h in offsets]
        elif candlestick_type in {"half-hour", "hour"}:
            offsets = [3, 4, 5, 6]
            anchors = [now.floor("h") - pd.Timedelta(hours=h) for h in offsets]
        else:
            offsets = [5, 6, 7]
            anchors = [now.floor("D") - pd.Timedelta(days=d) for d in offsets]
        return [int(a.value // 1_000_000) for a in anchors]

    def fetch_candlesticks(self, symbol: str, timeframe: str) -> pd.DataFrame:
        stock_id = to_stock_id(symbol)
        candlestick_type = TIMEFRAME_TO_CANDLESTICK[timeframe]
        self._prime_session(stock_id)

        stick = candlestick_type.replace("_", "-")
        live_base = f"/investrue/{stock_id.lower()}/{stick}-candlesticks"
        hist_base = f"/investrue/{stock_id.lower()}/historical-{stick}-candlesticks"

        rows: list[dict[str, Any]] = []
        for before_ms in self._historical_before_candidates(candlestick_type):
            try:
                rows.extend(self._get_json(f"{hist_base}?before={before_ms}"))
                break
            except Exception:
                continue
        try:
            live_path = live_base
            if rows:
                last_hist = max(r["time"] for r in rows)
                live_path = f"{live_base}?after={last_hist}"
            live_rows = self._get_json(live_path)
            if rows:
                last_hist = max(r["time"] for r in rows)
                live_rows = [r for r in live_rows if r["time"] > last_hist]
            rows.extend(live_rows)
        except Exception:
            pass

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
