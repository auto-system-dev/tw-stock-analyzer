"""掃描結果資料模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tw_stock_analyzer.analyzer.scoring import PotentialScore


@dataclass
class RankedStock:
    """單檔排名結果。"""

    symbol: str
    name: str
    score: PotentialScore
    direction: str
    fast_score: int = 0
    resonance_passed: int = 0
    resonance_total: int = 6

    @property
    def resonance_label(self) -> str:
        return f"{self.resonance_passed}/{self.resonance_total}"


@dataclass
class ScreenerResult:
    """批次掃描結果。"""

    universe_label: str
    scanned_count: int
    deep_scanned_count: int
    universe_total: int = 0
    skipped_count: int = 0
    batch_count: int = 1
    ranked: list[RankedStock] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=datetime.now)
    notes: list[str] = field(default_factory=list)
