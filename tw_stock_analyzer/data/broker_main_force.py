"""富邦 e-Broker 主力進出（免費 HTML 資料源）。"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from datetime import datetime

import pandas as pd
import requests

from tw_stock_analyzer.data.symbol_utils import to_stock_id

FUBON_BASE = "https://fubon-ebrokerdj.fbs.com.tw"
_REQUEST_GAP_SEC = 0.12
_HISTORY_ROW_RE = re.compile(
    r'<TD class="t4n0">(\d{4}/\d{2}/\d{2})</TD>\s*'
    r'<TD class="t3n1">([\d,]+)</TD>\s*'
    r'<TD class="t3n1">([\d,]+)</TD>\s*'
    r'<TD class="t3n1">([\d,]+)</TD>\s*'
    r'<TD class="t3(?:n1|r1)">(-?[\d,]+)</TD>',
    re.I | re.S,
)
_BROKER_LINK_RE = re.compile(
    r'zco0/zco0\.djhtm\?a=\d+&b=([^&"\']+)&BHID=([^&"\']+)"',
    re.I,
)


def _to_int(value: str) -> int:
    return int(value.replace(",", ""))


def _parse_broker_history(html: str) -> list[dict[str, int | str]]:
    rows: list[dict[str, int | str]] = []
    for match in _HISTORY_ROW_RE.finditer(html):
        rows.append(
            {
                "date": match.group(1),
                "buy_lots": _to_int(match.group(2)),
                "sell_lots": _to_int(match.group(3)),
                "net_lots": _to_int(match.group(5)),
            }
        )
    return rows


def _parse_broker_links(html: str) -> list[tuple[str, str]]:
    seen: set[str] = set()
    links: list[tuple[str, str]] = []
    for branch_id, house_id in _BROKER_LINK_RE.findall(html):
        key = house_id or branch_id
        if key in seen:
            continue
        seen.add(key)
        links.append((branch_id, house_id))
    return links


class FubonMainForceProvider:
    """自富邦主力進出頁彙總每日買進／賣出／淨張數（張）。"""

    def __init__(self, *, request_gap_sec: float = _REQUEST_GAP_SEC):
        self.request_gap_sec = request_gap_sec
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-TW,zh;q=0.9",
            }
        )

    def _get(self, path: str) -> str:
        response = self._session.get(f"{FUBON_BASE}{path}", timeout=30)
        response.encoding = response.apparent_encoding or "big5"
        response.raise_for_status()
        return response.text

    def fetch_daily_history(self, symbol: str) -> pd.DataFrame | None:
        """
        彙總當前主力分點近 ~20 個交易日的買賣張數。

        Returns:
            date, buy_lots, sell_lots, net_lots（買進−賣出）
        """
        stock_id = to_stock_id(symbol)
        overview_html = self._get(f"/z/zc/zco/zco.djhtm?a={stock_id}")
        broker_links = _parse_broker_links(overview_html)
        if not broker_links:
            return None

        by_date: dict[str, dict[str, int]] = defaultdict(
            lambda: {"buy_lots": 0, "sell_lots": 0}
        )
        for branch_id, house_id in broker_links:
            path = (
                f"/z/zc/zco/zco0/zco0.djhtm?a={stock_id}"
                f"&b={branch_id}&BHID={house_id}"
            )
            try:
                html = self._get(path)
            except requests.RequestException:
                continue
            for row in _parse_broker_history(html):
                date_key = str(row["date"])
                by_date[date_key]["buy_lots"] += int(row["buy_lots"])
                by_date[date_key]["sell_lots"] += int(row["sell_lots"])
            time.sleep(self.request_gap_sec)

        if not by_date:
            return None

        records: list[dict[str, object]] = []
        for date_s, totals in by_date.items():
            buy = totals["buy_lots"]
            sell = totals["sell_lots"]
            records.append(
                {
                    "date": datetime.strptime(date_s, "%Y/%m/%d"),
                    "buy_lots": buy,
                    "sell_lots": sell,
                    "net_lots": buy - sell,
                }
            )

        df = pd.DataFrame(records).sort_values("date").reset_index(drop=True)
        df["date"] = pd.to_datetime(df["date"])
        return df


def align_main_force_to_bars(
    bar_index: pd.DatetimeIndex,
    daily: pd.DataFrame,
) -> pd.DataFrame:
    """將每日主力資料對齊 K 線索引（僅有資料的交易日有值）。"""
    empty = pd.DataFrame(
        {
            "main_force_buy": pd.Series(index=bar_index, dtype=float),
            "main_force_sell": pd.Series(index=bar_index, dtype=float),
            "main_force_net": pd.Series(index=bar_index, dtype=float),
        }
    )
    if daily is None or daily.empty:
        return empty

    bars = pd.DataFrame({"bar_date": pd.to_datetime(bar_index).normalize()})
    hist = daily.sort_values("date").copy()
    hist["bar_date"] = pd.to_datetime(hist["date"]).dt.normalize()
    hist = hist.rename(
        columns={
            "buy_lots": "main_force_buy",
            "sell_lots": "main_force_sell",
            "net_lots": "main_force_net",
        }
    )
    merged = bars.merge(
        hist[["bar_date", "main_force_buy", "main_force_sell", "main_force_net"]],
        on="bar_date",
        how="left",
    )
    return merged[["main_force_buy", "main_force_sell", "main_force_net"]].set_axis(
        bar_index
    )
