"""市場脈絡資料模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FundamentalSnapshot:
    """基本面快照。"""

    pe_ratio: float | None = None
    pb_ratio: float | None = None
    eps: float | None = None
    revenue_latest: float | None = None
    revenue_yoy_pct: float | None = None
    dividend_yield_pct: float | None = None
    sources: list[str] = field(default_factory=list)


@dataclass
class InstitutionalFlow:
    """三大法人買賣彙總（近 N 日淨買超張數）。"""

    period_days: int
    foreign_net: float
    trust_net: float
    dealer_net: float
    total_net: float
    latest_date: str
    sources: list[str] = field(default_factory=list)


@dataclass
class NewsItem:
    """新聞 / 公告 / 社群消息。"""

    title: str
    source: str
    published_at: str
    link: str
    category: str  # 新聞 / 公告 / 社群
    summary: str = ""


@dataclass
class ThemeHit:
    """題材關鍵字命中。"""

    theme: str
    score: int
    keywords: list[str] = field(default_factory=list)


@dataclass
class MarketContext:
    """消息面 + 基本面 + 籌碼 + 題材。"""

    fundamentals: FundamentalSnapshot
    institutional: InstitutionalFlow | None
    news: list[NewsItem] = field(default_factory=list)
    announcements: list[NewsItem] = field(default_factory=list)
    social: list[NewsItem] = field(default_factory=list)
    themes: list[ThemeHit] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def themes_summary(self) -> str:
        if not self.themes:
            return "未偵測到明顯題材關鍵字"
        return "、".join(t.theme for t in self.themes[:5])
