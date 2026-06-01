"""機器學習價格趨勢預測與訊號綜合。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from tw_stock_analyzer.predictor.signals import (
    aggregate_direction,
    rule_signals_from_row,
)


@dataclass
class PredictionResult:
    """預測結果。"""

    current_price: float
    predicted_price: float
    predicted_change_pct: float
    direction: str  # 看多 / 看空 / 中性
    confidence: float  # 0~1，基於測試集 R²
    horizon_days: int
    signals: dict[str, str]


FEATURE_COLUMNS = [
    "sma_5",
    "sma_20",
    "sma_60",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "bb_middle",
    "bb_lower",
    "volatility_20d",
    "return_1d",
]


class PricePredictor:
    """使用 Random Forest 預測 N 日後收盤價相對變化。"""

    def __init__(self, horizon_days: int = 5):
        self.horizon_days = horizon_days
        self._model: RandomForestRegressor | None = None
        self._scaler = StandardScaler()
        self._r2_score: float = 0.0

    def _prepare_dataset(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        data = df.copy()
        data["target"] = data["close"].shift(-self.horizon_days) / data["close"] - 1
        data = data.dropna()

        X = data[FEATURE_COLUMNS].values
        y = data["target"].values
        return X, y

    def train(self, df: pd.DataFrame) -> float:
        """訓練模型，回傳測試集 R²。"""
        X, y = self._prepare_dataset(df)
        if len(X) < 60:
            raise ValueError("資料筆數不足，請延長擷取期間（至少約 3 個月）。")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )
        X_train_scaled = self._scaler.fit_transform(X_train)
        X_test_scaled = self._scaler.transform(X_test)

        self._model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            random_state=42,
            n_jobs=-1,
        )
        self._model.fit(X_train_scaled, y_train)
        self._r2_score = float(self._model.score(X_test_scaled, y_test))
        return self._r2_score

    def predict(self, df: pd.DataFrame) -> PredictionResult:
        """對最新一筆資料進行預測。"""
        if self._model is None:
            self.train(df)

        latest = df.iloc[-1]
        current_price = float(latest["close"])
        X = latest[FEATURE_COLUMNS].values.reshape(1, -1)
        X_scaled = self._scaler.transform(X)
        predicted_change = float(self._model.predict(X_scaled)[0])
        predicted_price = current_price * (1 + predicted_change)

        signals = rule_signals_from_row(latest)
        direction = aggregate_direction(predicted_change, signals, use_ml=True)

        return PredictionResult(
            current_price=current_price,
            predicted_price=round(predicted_price, 2),
            predicted_change_pct=round(predicted_change * 100, 2),
            direction=direction,
            confidence=max(0.0, min(1.0, self._r2_score)),
            horizon_days=self.horizon_days,
            signals=signals,
        )

