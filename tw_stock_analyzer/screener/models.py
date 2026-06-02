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


@dataclass
class ScreenerResult:
    """批次掃描結果。"""

    universe_label: str
    scanned_count: int
    deep_scanned_count: int
    ranked: list[RankedStock] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=datetime.now)
    notes: list[str] = field(default_factory=list)
