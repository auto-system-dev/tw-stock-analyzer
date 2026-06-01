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

    def get_data(
        self,
        dataset: str,
        data_id: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame | None:
        params = {
            "dataset": dataset,
            "data_id": data_id,
            "start_date": start_date,
            "end_date": end_date,
        }
        try:
            resp = self._session.get(API_BASE, params=params, timeout=60)
            resp.raise_for_status()
            body = resp.json()
            rows = body.get("data")
            if not rows:
                return None
            return pd.DataFrame(rows)
        except Exception:
            return None

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


@lru_cache(maxsize=1)
def get_finmind_client() -> FinMindApiClient:
    return FinMindApiClient()
