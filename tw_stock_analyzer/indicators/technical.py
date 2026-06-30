"""技術指標計算。"""

from __future__ import annotations

import pandas as pd
from tw_stock_analyzer.indicators.ta_pure import (
    BollingerBands,
    MACD,
    RSIIndicator,
    SMAIndicator,
)


class TechnicalIndicators:
    """在 OHLCV DataFrame 上計算常用技術指標。"""

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        result = df.copy()
        close = result["close"]

        result["sma_50"] = SMAIndicator(close, window=50).sma_indicator()
        result["sma_200"] = SMAIndicator(close, window=200).sma_indicator()

        result["rsi_14"] = RSIIndicator(close, window=14).rsi()

        macd = MACD(close)
        result["macd"] = macd.macd()
        result["macd_signal"] = macd.macd_signal()
        result["macd_hist"] = macd.macd_diff()

        bb = BollingerBands(close, window=20, window_dev=2)
        result["bb_upper"] = bb.bollinger_hband()
        result["bb_middle"] = bb.bollinger_mavg()
        result["bb_lower"] = bb.bollinger_lband()

        result["return_1d"] = close.pct_change()
        result["volatility_20d"] = result["return_1d"].rolling(20).std()
        result["volatility_5d"] = result["return_1d"].rolling(5).std()

        vol_ma5 = result["volume"].rolling(5).mean()
        result["volume_ratio_5d"] = result["volume"] / vol_ma5

        high_52w = close.rolling(252, min_periods=60).max()
        result["pct_from_52w_high"] = close / high_52w - 1

        result["volatility_ratio"] = result["volatility_5d"] / result[
            "volatility_20d"
        ].replace(0, float("nan"))

        return result.dropna()
