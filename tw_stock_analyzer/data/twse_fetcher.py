"""臺灣證券交易所日線資料（OpenAPI + 官網 rwd API）。"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
import requests

from tw_stock_analyzer.data.symbol_utils import to_stock_id

TWSE_OPENAPI_BASE = "https://openapi.twse.com.tw/v1"
TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"

PERIOD_DAYS: dict[str, int] = {
    "1mo": 31,
    "3mo": 92,
    "6mo": 183,
    "1y": 365,
    "2y": 730,
    "5y": 1825,
    "10y": 3650,
    "max": 7300,
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


class TwseDailyFetcher:
    """擷取上市個股日 K（成交量為股數）。"""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)

    def fetch(self, symbol: str, period: str = "2y") -> pd.DataFrame:
        stock_id = to_stock_id(symbol)
        if not re.fullmatch(r"\d{4,6}", stock_id):
            raise ValueError(f"{symbol} 非台股數字代號，無法使用 TWSE 日線。")

        start = self._period_start(period)
        rows = self._fetch_monthly_history(stock_id, start)
        if not rows:
            raise ValueError(f"TWSE 無 {stock_id} 日線資料。")

        df = pd.DataFrame(rows).set_index("date").sort_index()
        if df.index.duplicated().any():
            df = df.groupby(level=0).agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                }
            )
        start_cut = start.tz_localize(None) if getattr(start, "tz", None) is not None else start
        df = df.loc[df.index >= start_cut]
        if df.empty:
            raise ValueError(f"TWSE 在指定期間內無 {stock_id} 日線資料。")

        df.attrs["symbol"] = f"{stock_id}.TW"
        df.attrs["source"] = "twse"
        return df

    def _period_start(self, period: str) -> pd.Timestamp:
        days = PERIOD_DAYS.get(period, PERIOD_DAYS["2y"])
        return (pd.Timestamp.now(tz="Asia/Taipei") - pd.Timedelta(days=days)).normalize()

    def _fetch_monthly_history(
        self, stock_id: str, start: pd.Timestamp
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor = pd.Timestamp.now(tz="Asia/Taipei").normalize().tz_localize(None)
        start_cut = start.tz_localize(None) if getattr(start, "tz", None) is not None else start

        while cursor >= start_cut:
            month_rows = self._fetch_month(stock_id, cursor.year, cursor.month)
            rows.extend(month_rows)
            cursor = (cursor.replace(day=1) - pd.Timedelta(days=1)).normalize()

        return rows

    def _month_anchor(self, year: int, month: int) -> str:
        now = pd.Timestamp.now(tz="Asia/Taipei")
        if year == now.year and month == now.month:
            day = now.day
        else:
            day = 5
        return f"{year}{month:02d}{day:02d}"

    def _fetch_month(self, stock_id: str, year: int, month: int) -> list[dict[str, Any]]:
        payload = None
        for anchor in self._month_anchor_candidates(year, month):
            resp = self._session.get(
                TWSE_STOCK_DAY_URL,
                params={"date": anchor, "stockNo": stock_id, "response": "json"},
                timeout=30,
            )
            resp.raise_for_status()
            candidate = resp.json()
            if candidate.get("stat") == "OK":
                payload = candidate
                break
        if payload is None:
            return []

        fields = payload.get("fields") or []
        try:
            date_i = fields.index("日期")
            vol_i = fields.index("成交股數")
            open_i = fields.index("開盤價")
            high_i = fields.index("最高價")
            low_i = fields.index("最低價")
            close_i = fields.index("收盤價")
        except ValueError as exc:
            raise ValueError(f"TWSE STOCK_DAY 欄位格式異常：{fields}") from exc

        rows: list[dict[str, Any]] = []
        for raw in payload.get("data") or []:
            if not raw or len(raw) <= close_i:
                continue
            date = self._parse_roc_date(raw[date_i])
            if date is None:
                continue
            rows.append(
                {
                    "date": date,
                    "open": self._parse_number(raw[open_i]),
                    "high": self._parse_number(raw[high_i]),
                    "low": self._parse_number(raw[low_i]),
                    "close": self._parse_number(raw[close_i]),
                    "volume": self._parse_volume(raw[vol_i]),
                }
            )
        return rows

    def _month_anchor_candidates(self, year: int, month: int) -> list[str]:
        primary = self._month_anchor(year, month)
        candidates = [primary]
        if not (year == pd.Timestamp.now(tz="Asia/Taipei").year and month == pd.Timestamp.now(tz="Asia/Taipei").month):
            candidates.append(f"{year}{month:02d}15")
        return candidates

    @staticmethod
    def _parse_roc_date(value: str) -> pd.Timestamp | None:
        text = str(value).strip()
        match = re.fullmatch(r"(\d{2,3})/(\d{2})/(\d{2})", text)
        if not match:
            return None
        year = int(match.group(1)) + 1911
        month = int(match.group(2))
        day = int(match.group(3))
        return pd.Timestamp(year=year, month=month, day=day)

    @staticmethod
    def _parse_number(value: str) -> float:
        text = str(value).strip().replace(",", "")
        if not text or text in {"-", "--", "X0.00"}:
            return float("nan")
        return float(text)

    @staticmethod
    def _parse_volume(value: str) -> float:
        text = str(value).strip().replace(",", "")
        if not text or text == "-":
            return 0.0
        return float(text)

    def fetch_latest_openapi_row(self, stock_id: str) -> dict[str, Any] | None:
        """OpenAPI 單日全市場快照（用於交叉驗證最新交易日）。"""
        resp = self._session.get(
            f"{TWSE_OPENAPI_BASE}/exchangeReport/STOCK_DAY_ALL",
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return None
        return next((row for row in data if row.get("Code") == stock_id), None)
