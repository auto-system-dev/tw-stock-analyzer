"""社群 / 公開討論（Google News RSS 近似）。"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import quote
from urllib.request import urlopen

from tw_stock_analyzer.data.models import NewsItem
from tw_stock_analyzer.data.symbol_utils import to_stock_id


class SocialProvider:
    """
    以 Google News RSS 搜尋「代號 + 台股」相關討論。
    非即時社群 API，僅作輔助參考。
    """

    def __init__(self, max_items: int = 10):
        self.max_items = max_items

    def fetch(self, symbol: str, name: str = "") -> list[NewsItem]:
        stock_id = to_stock_id(symbol)
        query = quote(f"{stock_id} {name} 台股".strip())
        url = (
            f"https://news.google.com/rss/search?q={query}"
            "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        )
        try:
            with urlopen(url, timeout=10) as resp:
                xml_data = resp.read()
        except Exception:
            return []

        return self._parse_rss(xml_data)

    def _parse_rss(self, xml_data: bytes) -> list[NewsItem]:
        items: list[NewsItem] = []
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError:
            return []

        for elem in root.iter("item"):
            title = _text(elem, "title")
            link = _text(elem, "link")
            pub = _text(elem, "pubDate")
            published = _format_pub(pub)
            if not title:
                continue
            items.append(
                NewsItem(
                    title=title,
                    source="Google News",
                    published_at=published,
                    link=link,
                    category="社群",
                    summary="",
                )
            )
            if len(items) >= self.max_items:
                break
        return items


def _text(parent, tag: str) -> str:
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else ""


def _format_pub(pub: str) -> str:
    if not pub:
        return "—"
    try:
        dt = datetime.strptime(pub[:25], "%a, %d %b %Y %H:%M:%S")
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return pub[:16]
