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
    resonance_full_only: bool = False
    resonance_min: int | None = None

    def passes_resonance(self, passed: int, total: int) -> bool:
        if self.resonance_full_only:
            return passed == total
        if self.resonance_min is not None:
            return passed >= self.resonance_min
        return True

    def passes(
        self,
        total: int,
        direction: str,
        revenue_yoy: float | None,
        *,
        resonance_passed: int = 0,
        resonance_total: int = 6,
    ) -> bool:
        if total < self.min_score:
            return False
        if self.bullish_only and direction != "看多":
            return False
        if self.min_revenue_yoy is not None:
            if revenue_yoy is None or revenue_yoy < self.min_revenue_yoy:
                return False
        if not self.passes_resonance(resonance_passed, resonance_total):
            return False
        return True
