"""FinMind REST API v4（不需安裝 finmind 套件，避免與 ta 衝突）。"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from functools import lru_cache

import pandas as pd
import requests

API_BASE = "https://api.finmindtrade.com/api/v4/data"


class FinMindApiClient:
    """透過 HTTP 取得 FinMind 開放資料。"""

    def __init__(self) -> None:
        self._token = os.getenv("FINMIND_API_TOKEN", "").strip()
        self._session = requests.Session()
        if self._token:
            self._session.headers["Authorization"] = f"Bearer {self._token}"

    @property
    def has_token(self) -> bool:
        return bool(self._token)

    def get_data_with_status(
        self,
        dataset: str,
        data_id: str,
        start_date: str,
        end_date: str | None = None,
    ) -> tuple[pd.DataFrame | None, int, str | None]:
        """回傳 (DataFrame, HTTP status, error_message)。"""
        params = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
            "end_date": end_date or start_date,
        }
        try:
            resp = self._session.get(API_BASE, params=params, timeout=60)
            status = resp.status_code
            if not resp.ok:
                return None, status, resp.text[:240]
            body = resp.json()
            rows = body.get("data")
            if not rows:
                return None, status, "empty"
            return pd.DataFrame(rows), status, None
        except Exception as exc:
            return None, 0, str(exc)

    def get_data(
        self,
        dataset: str,
        data_id: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame | None:
        df, _, _ = self.get_data_with_status(dataset, data_id, start_date, end_date)
        return df

    def fetch(
        self,
        dataset: str,
        stock_id: str,
        days: int = 90,
    ) -> pd.DataFrame | None:
        end = datetime.now().date()
        start = end - timedelta(days=days)
        return self.get_data(
            dataset=dataset,
            data_id=stock_id,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

    def fetch_dataset(
        self,
        dataset: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame | None:
        """取得整個 dataset（不指定 data_id）。"""
        end = end_date or datetime.now().date().isoformat()
        start = start_date or (datetime.now().date() - timedelta(days=7)).isoformat()
        params: dict[str, str] = {
            "dataset": dataset,
            "start_date": start,
            "end_date": end,
        }
        try:
            resp = self._session.get(API_BASE, params=params, timeout=120)
            resp.raise_for_status()
            body = resp.json()
            rows = body.get("data")
            if not rows:
                return None
            return pd.DataFrame(rows)
        except Exception:
            return None

    def fetch_stock_list(self) -> list[str]:
        """取得上市股票代號清單（FinMind TaiwanStockInfo）。"""
        df = self.fetch_dataset("TaiwanStockInfo")
        if df is None or df.empty:
            return []
        id_col = "stock_id" if "stock_id" in df.columns else "data_id"
        if id_col not in df.columns:
            return []
        codes = df[id_col].astype(str).str.strip()
        codes = codes[codes.str.match(r"^\d{4}$", na=False)]
        return sorted(codes.unique().tolist())


@lru_cache(maxsize=1)
def get_finmind_client() -> FinMindApiClient:
    return FinMindApiClient()
