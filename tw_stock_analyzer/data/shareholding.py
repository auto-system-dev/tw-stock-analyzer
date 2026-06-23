"""集保戶股權分散：持股 1000 張以上比例（TDCC）。"""

from __future__ import annotations

import re
import time
from datetime import datetime

import pandas as pd
import requests

from tw_stock_analyzer.data.symbol_utils import to_stock_id

TDCC_QRY_URL = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
# 集保分級以「股」為單位；千張大戶 = 1,000,001 股以上（第 15 級）
TDCC_TIER_1000_LOTS = 15
_REQUEST_GAP_SEC = 0.15


def _parse_hidden(html: str, name: str) -> str:
    match = re.search(rf'name="{name}"\s+value="([^"]*)"', html)
    if not match:
        raise ValueError(f"TDCC 表單缺少 {name}")
    return match.group(1)


def _parse_tiers(html: str) -> list[tuple[int, float]]:
    rows: list[tuple[int, float]] = []
    pattern = re.compile(
        r"<tr>\s*<td[^>]*>(\d+)</td>\s*<td[^>]*>[^<]+</td>"
        r"\s*<td[^>]*>[\d,]+</td>\s*<td[^>]*>[\d,]+</td>\s*<td[^>]*>([\d.]+)</td>\s*</tr>"
    )
    for tier_s, pct_s in pattern.findall(html):
        rows.append((int(tier_s), float(pct_s)))
    return rows


def _available_dates(session: requests.Session) -> list[str]:
    html = session.get(TDCC_QRY_URL, timeout=30).text
    dates = re.findall(r'<option value="(\d{8})"\s*>', html)
    return list(dict.fromkeys(dates))


def _fetch_ratio_for_date(
    session: requests.Session,
    stock_id: str,
    date: str,
    *,
    form_html: str | None = None,
) -> float | None:
    html = form_html or session.get(TDCC_QRY_URL, timeout=30).text
    payload = {
        "SYNCHRONIZER_TOKEN": _parse_hidden(html, "SYNCHRONIZER_TOKEN"),
        "SYNCHRONIZER_URI": _parse_hidden(html, "SYNCHRONIZER_URI"),
        "method": "submit",
        "firDate": _parse_hidden(html, "firDate"),
        "scaDate": date,
        "sqlMethod": "StockNo",
        "stockNo": stock_id,
        "stockName": "",
    }
    resp = session.post(TDCC_QRY_URL, data=payload, timeout=30)
    tiers = _parse_tiers(resp.text)
    if not tiers:
        return None
    for tier, pct in tiers:
        if tier == TDCC_TIER_1000_LOTS:
            return round(pct, 4)
    return None


class ShareholdingProvider:
    """自 TDCC 集保戶股權分散表取得千張大戶持股比例歷史。"""

    def __init__(self, weeks: int = 26):
        self.weeks = weeks

    def fetch_over_1000_ratio_history(self, symbol: str) -> pd.DataFrame | None:
        """回傳 columns: date (Timestamp), ratio (float, %)."""
        stock_id = to_stock_id(symbol)
        session = requests.Session()
        session.headers["User-Agent"] = "Mozilla/5.0"

        dates = _available_dates(session)
        if not dates:
            return None

        selected = dates[: self.weeks]
        records: list[dict[str, object]] = []
        for date_s in reversed(selected):
            form_html = session.get(TDCC_QRY_URL, timeout=30).text
            ratio = _fetch_ratio_for_date(
                session, stock_id, date_s, form_html=form_html
            )
            if ratio is not None:
                records.append(
                    {
                        "date": datetime.strptime(date_s, "%Y%m%d"),
                        "ratio": ratio,
                    }
                )
            time.sleep(_REQUEST_GAP_SEC)

        if not records:
            return None

        df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])
        return df


def align_over_1000_ratio_to_bars(
    bar_index: pd.DatetimeIndex,
    weekly: pd.DataFrame,
) -> pd.Series:
    """將週更新集保比例前向填充至每根 K 線（每日一根柱、十字線同步）。"""
    if weekly is None or weekly.empty:
        return pd.Series(index=bar_index, dtype=float)

    bars = pd.DataFrame({"bar_date": pd.to_datetime(bar_index).normalize()})
    w = (
        weekly.sort_values("date")[["date", "ratio"]]
        .rename(columns={"date": "bar_date", "ratio": "over_1000_ratio"})
        .copy()
    )
    w["bar_date"] = pd.to_datetime(w["bar_date"]).dt.normalize()
    merged = pd.merge_asof(bars, w, on="bar_date", direction="backward")
    return merged["over_1000_ratio"].set_axis(bar_index)
