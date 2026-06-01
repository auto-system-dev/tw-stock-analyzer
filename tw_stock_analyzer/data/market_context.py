"""整合消息面、基本面、籌碼、題材。"""

from __future__ import annotations

import os

from tw_stock_analyzer.data.fundamentals import FundamentalsProvider
from tw_stock_analyzer.data.institutional import InstitutionalProvider
from tw_stock_analyzer.data.models import MarketContext
from tw_stock_analyzer.data.news_provider import NewsProvider
from tw_stock_analyzer.data.social import SocialProvider
from tw_stock_analyzer.data.themes import ThemeDetector


class MarketContextProvider:
    """擷取完整市場脈絡。"""

    def __init__(self, institutional_days: int = 5):
        self.fundamentals = FundamentalsProvider()
        self.institutional = InstitutionalProvider(period_days=institutional_days)
        self.news = NewsProvider()
        self.social = SocialProvider()
        self.themes = ThemeDetector()

    def fetch(self, symbol: str, name: str = "") -> MarketContext:
        notes: list[str] = []
        fund = self.fundamentals.fetch(symbol)
        inst = self.institutional.fetch(symbol)
        if inst is None:
            notes.append(
                "籌碼：需設定 FINMIND_API_TOKEN（https://finmindtrade.com/）"
            )

        news_items, announcements = self.news.fetch(symbol)
        if not news_items and not announcements:
            notes.append("新聞：Yahoo / FinMind 暫無資料")

        social_items = self.social.fetch(symbol, name)
        if not social_items:
            notes.append("社群：Google News RSS 未取得結果（可能為網路限制）")

        if not os.getenv("FINMIND_API_TOKEN", "").strip():
            notes.append(
                "建議至 https://finmindtrade.com/ 註冊並設定環境變數 FINMIND_API_TOKEN 以提高資料完整度"
            )

        all_text = news_items + announcements + social_items
        theme_hits = self.themes.detect(all_text)

        return MarketContext(
            fundamentals=fund,
            institutional=inst,
            news=news_items,
            announcements=announcements,
            social=social_items,
            themes=theme_hits,
            notes=notes,
        )


def ensure_report_market_context(report) -> MarketContext:
    """相容舊版快取：報告缺少 market_context 時即時補抓。"""
    ctx = getattr(report, "market_context", None)
    if ctx is not None:
        return ctx
    stock_id = str(report.symbol).split(".")[0]
    ctx = MarketContextProvider().fetch(stock_id, report.name)
    report.market_context = ctx
    return ctx
