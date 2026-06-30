"""純 pandas 技術指標（取代 ta 套件，避免 Docker 建置需編譯 sdist）。"""

from __future__ import annotations

import pandas as pd


class SMAIndicator:
    def __init__(self, close: pd.Series, window: int) -> None:
        self._close = close
        self._window = window

    def sma_indicator(self) -> pd.Series:
        return self._close.rolling(self._window).mean()


class RSIIndicator:
    def __init__(self, close: pd.Series, window: int = 14) -> None:
        self._close = close
        self._window = window

    def rsi(self) -> pd.Series:
        delta = self._close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = gain.ewm(
            alpha=1 / self._window, min_periods=self._window, adjust=False
        ).mean()
        avg_loss = loss.ewm(
            alpha=1 / self._window, min_periods=self._window, adjust=False
        ).mean()
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        return 100 - (100 / (1 + rs))


class MACD:
    def __init__(
        self,
        close: pd.Series,
        window_slow: int = 26,
        window_fast: int = 12,
        window_sign: int = 9,
    ) -> None:
        self._close = close
        self._fast = window_fast
        self._slow = window_slow
        self._sign = window_sign

    def macd(self) -> pd.Series:
        fast = self._close.ewm(span=self._fast, adjust=False).mean()
        slow = self._close.ewm(span=self._slow, adjust=False).mean()
        return fast - slow

    def macd_signal(self) -> pd.Series:
        return self.macd().ewm(span=self._sign, adjust=False).mean()

    def macd_diff(self) -> pd.Series:
        return self.macd() - self.macd_signal()


class BollingerBands:
    def __init__(
        self,
        close: pd.Series,
        window: int = 20,
        window_dev: float = 2,
    ) -> None:
        self._close = close
        self._window = window
        self._dev = window_dev

    def bollinger_mavg(self) -> pd.Series:
        return self._close.rolling(self._window).mean()

    def bollinger_hband(self) -> pd.Series:
        mavg = self.bollinger_mavg()
        std = self._close.rolling(self._window).std()
        return mavg + self._dev * std

    def bollinger_lband(self) -> pd.Series:
        mavg = self.bollinger_mavg()
        std = self._close.rolling(self._window).std()
        return mavg - self._dev * std
