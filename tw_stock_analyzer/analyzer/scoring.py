"""多維度潛力股評分。"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from tw_stock_analyzer.data.models import MarketContext
from tw_stock_analyzer.predictor.model import PredictionResult
from tw_stock_analyzer.predictor.signals import rules_score


HOLDING_PERIOD_HINTS: dict[str, str] = {
    "短線": "約 1～2 週",
    "波段": "約 2～8 週",
    "中期": "約 1～3 個月",
    "長期": "約 3 個月以上",
}


@dataclass
class PotentialScore:
    """潛力股綜合評分（0–100）。"""

    total: int
    technical: int
    fundamental: int
    institutional: int
    theme: int
    momentum: int
    grade: str
    holding_type: str
    holding_period: str
    reasons: list[str] = field(default_factory=list)


def _grade_from_total(total: int) -> str:
    if total >= 75:
        return "A"
    if total >= 60:
        return "B"
    if total >= 45:
        return "C"
    return "D"


def _infer_holding_type(
    technical: int,
    fundamental: int,
    institutional: int,
    theme: int,
    momentum: int,
) -> tuple[str, str]:
    """
    依各維度得分推估持有類型。

    短線：題材 + 動能為主
    波段：籌碼 + 動能 + 技術為主
    中期：基本面 + 籌碼為主
    長期：基本面為主且題材權重低
    """
    weights = {
        "短線": theme * 3 + momentum * 2 + technical * 0.5,
        "波段": momentum * 2 + institutional * 2 + technical + theme * 0.5,
        "中期": fundamental * 2.5 + institutional,
        "長期": fundamental * 2.5 + institutional * 0.5 - theme * 1.5,
    }
    holding_type = max(weights, key=weights.get)
    return holding_type, HOLDING_PERIOD_HINTS[holding_type]


def _score_technical(
    signals: dict[str, str],
    prediction: PredictionResult | None,
    *,
    use_ml: bool,
    reasons: list[str],
) -> int:
    raw = rules_score(signals)
    base = int((raw + 4) / 8 * 20)
    base = max(0, min(20, base))

    ml_bonus = 0
    if use_ml and prediction is not None:
        if prediction.predicted_change_pct > 1.0:
            ml_bonus = 5
            reasons.append(f"ML 預估 {prediction.horizon_days} 日後上漲 {prediction.predicted_change_pct:+.2f}%")
        elif prediction.predicted_change_pct < -1.0:
            ml_bonus = 0
            reasons.append(f"ML 預估 {prediction.horizon_days} 日後下跌 {prediction.predicted_change_pct:+.2f}%")
        else:
            ml_bonus = 2

    if signals.get("均線") == "多頭排列":
        reasons.append("均線多頭排列")
    elif signals.get("均線") == "空頭排列":
        reasons.append("均線空頭排列")

    return min(25, base + ml_bonus)


def _score_fundamental(ctx: MarketContext, reasons: list[str]) -> int:
    f = ctx.fundamentals
    score = 0

    if f.revenue_yoy_pct is not None:
        if f.revenue_yoy_pct > 20:
            score += 8
            reasons.append(f"月營收 YoY {f.revenue_yoy_pct:+.1f}%（強勁）")
        elif f.revenue_yoy_pct > 10:
            score += 4
            reasons.append(f"月營收 YoY {f.revenue_yoy_pct:+.1f}%")

    if f.pe_ratio is not None and f.pe_ratio > 0:
        if 10 <= f.pe_ratio <= 30:
            score += 5
            reasons.append(f"PER {f.pe_ratio:.1f} 合理")
        elif f.pe_ratio < 10 or f.pe_ratio <= 50:
            score += 2

    if f.pb_ratio is not None and f.pb_ratio > 0:
        if f.pb_ratio < 2:
            score += 5
            reasons.append(f"PBR {f.pb_ratio:.2f} 偏低")
        elif f.pb_ratio < 3:
            score += 2

    if f.eps is not None and f.eps > 0:
        score += 5
        reasons.append(f"EPS {f.eps:.2f} 為正")

    return min(25, score)


def _score_institutional(ctx: MarketContext, reasons: list[str]) -> int:
    inst = ctx.institutional
    if inst is None:
        return 0

    score = 0
    if inst.total_net > 1000:
        score += 15
        reasons.append(f"近{inst.period_days}日法人淨買超 {inst.total_net:,.0f} 張")
    elif inst.total_net > 500:
        score += 10
    elif inst.total_net > 0:
        score += 5

    if inst.foreign_net > 0 and inst.trust_net > 0:
        score += 10
        reasons.append("外資與投信同步買超")

    return min(25, score)


def _score_theme(ctx: MarketContext, reasons: list[str]) -> int:
    if not ctx.themes:
        return 0
    score = min(10, sum(min(t.score, 3) for t in ctx.themes[:4]))
    if score > 0:
        themes = "、".join(t.theme for t in ctx.themes[:3])
        reasons.append(f"題材：{themes}")
    return score


def _score_momentum(latest: pd.Series, signals: dict[str, str], reasons: list[str]) -> int:
    score = 0

    vol_ratio = float(latest.get("volume_ratio_5d", 1.0))
    if vol_ratio > 1.5:
        score += 5
        reasons.append(f"量比 {vol_ratio:.2f}（放量）")
    elif vol_ratio > 1.2:
        score += 3

    pct_high = float(latest.get("pct_from_52w_high", -1.0))
    if pct_high > -0.10:
        score += 5
        reasons.append(f"距 52 週高點 {pct_high * 100:.1f}%")
    elif pct_high > -0.20:
        score += 3

    if signals.get("均線") == "多頭排列":
        score += 5

    return min(15, score)


def compute_potential_score(
    latest: pd.Series,
    signals: dict[str, str],
    market_context: MarketContext,
    prediction: PredictionResult | None = None,
    *,
    use_ml: bool = True,
) -> PotentialScore:
    """計算多維度潛力評分。"""
    reasons: list[str] = []

    technical = _score_technical(signals, prediction, use_ml=use_ml, reasons=reasons)
    fundamental = _score_fundamental(market_context, reasons)
    institutional = _score_institutional(market_context, reasons)
    theme = _score_theme(market_context, reasons)
    momentum = _score_momentum(latest, signals, reasons)

    total = technical + fundamental + institutional + theme + momentum
    grade = _grade_from_total(total)
    holding_type, holding_period = _infer_holding_type(
        technical, fundamental, institutional, theme, momentum
    )

    return PotentialScore(
        total=total,
        technical=technical,
        fundamental=fundamental,
        institutional=institutional,
        theme=theme,
        momentum=momentum,
        grade=grade,
        holding_type=holding_type,
        holding_period=holding_period,
        reasons=reasons[:8],
    )
