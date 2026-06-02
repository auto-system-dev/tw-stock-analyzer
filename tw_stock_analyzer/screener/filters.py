"""掃描篩選條件。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScreenerFilters:
    """潛力股掃描篩選參數。"""

    min_score: int = 0
    top_n: int = 10
    deep_candidates: int = 50
    bullish_only: bool = False
    min_revenue_yoy: float | None = None

    def passes(self, total: int, direction: str, revenue_yoy: float | None) -> bool:
        if total < self.min_score:
            return False
        if self.bullish_only and direction != "看多":
            return False
        if self.min_revenue_yoy is not None:
            if revenue_yoy is None or revenue_yoy < self.min_revenue_yoy:
                return False
        return True
