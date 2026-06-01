"""新聞與公告。"""

from __future__ import annotations

from datetime import datetime

import yfinance as yf

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.models import NewsItem
from tw_stock_analyzer.data.symbol_utils import normalize_symbol, to_stock_id


class NewsProvider:
    """Yahoo Finance + FinMind 台股新聞。"""

    def __init__(self, max_items: int = 15):
        self.max_items = max_items

    def fetch(self, symbol: str) -> tuple[list[NewsItem], list[NewsItem]]:
        """回傳 (新聞, 公告式新聞)。"""
        items: list[NewsItem] = []
        announcements: list[NewsItem] = []

        items.extend(self._from_yfinance(symbol))
        finmind_news = self._from_finmind(symbol)
        for n in finmind_news:
            if _is_announcement(n.title):
                announcements.append(n)
            else:
                items.append(n)

        items = _dedupe(items)[: self.max_items]
        announcements = _dedupe(announcements)[: self.max_items]
        return items, announcements

    def _from_yfinance(self, symbol: str) -> list[NewsItem]:
        ticker = normalize_symbol(symbol)
        try:
            raw = yf.Ticker(ticker).news or []
        except Exception:
            return []

        result = []
        for n in raw[: self.max_items]:
            ts = n.get("providerPublishTime")
            published = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                if ts
                else "—"
            )
            result.append(
                NewsItem(
                    title=n.get("title", "—"),
                    source=n.get("publisher", "Yahoo"),
                    published_at=published,
                    link=n.get("link", ""),
                    category="新聞",
                    summary=n.get("summary", "") or "",
                )
            )
        return result

    def _from_finmind(self, symbol: str) -> list[NewsItem]:
        stock_id = to_stock_id(symbol)
        client = get_finmind_client()
        df = client.fetch("TaiwanStockNews", stock_id, days=60)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.head(self.max_items).iterrows():
            result.append(
                NewsItem(
                    title=str(row.get("title", "—")),
                    source=str(row.get("source", "FinMind")),
                    published_at=str(row.get("date", "—")),
                    link=str(row.get("link", "") or ""),
                    category="新聞",
                    summary=str(row.get("description", "") or "")[:200],
                )
            )
        return result


def _is_announcement(title: str) -> bool:
    keys = ("公告", "重訊", "董事會", "除權", "除息", "增資", "減資", "配股", "法說會")
    return any(k in title for k in keys)


def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
    seen: set[str] = set()
    out = []
    for item in items:
        key = item.title[:40]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
