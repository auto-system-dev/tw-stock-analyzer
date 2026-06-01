"""題材關鍵字偵測（AI、法說、訂單等）。"""

from __future__ import annotations

import re

from tw_stock_analyzer.data.models import NewsItem, ThemeHit

THEME_PATTERNS: dict[str, list[str]] = {
    "AI": [
        r"AI",
        r"人工智慧",
        r"生成式",
        r"GPU",
        r"晶片",
        r"CoWoS",
        r"先進製程",
        r"HBM",
    ],
    "法說": [
        r"法說",
        r"法人說明會",
        r"財報",
        r"季報",
        r"年報",
        r"EPS",
        r"盈餘",
    ],
    "訂單": [
        r"訂單",
        r"接單",
        r"合作",
        r"簽約",
        r"投資",
        r"擴產",
        r"資本支出",
        r"客戶",
    ],
    "股利": [r"股利", r"配息", r"除權", r"除息", r"股息"],
    "法規": [r"法規", r"裁罰", r"調查", r"起訴", r"罰款", r"禁止"],
    "總經": [r"升息", r"降息", r"通膨", r"關稅", r"匯率", r"Fed", r"央行"],
}


class ThemeDetector:
    """從新聞與社群標題比對題材。"""

    def detect(self, items: list[NewsItem], top_n: int = 6) -> list[ThemeHit]:
        scores: dict[str, tuple[int, set[str]]] = {}
        for item in items:
            text = f"{item.title} {item.summary}"
            for theme, patterns in THEME_PATTERNS.items():
                for pat in patterns:
                    if re.search(pat, text, re.IGNORECASE):
                        score, kws = scores.get(theme, (0, set()))
                        scores[theme] = (score + 1, kws | {pat})

        hits = [
            ThemeHit(theme=t, score=s, keywords=sorted(kws)[:5])
            for t, (s, kws) in scores.items()
            if s > 0
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_n]
