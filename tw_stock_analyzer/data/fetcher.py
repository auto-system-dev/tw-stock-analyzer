"""擷取台股歷史資料：日線優先 TWSE / FinMind，Yahoo 為最後備援。"""

from __future__ import annotations

import logging
import re

import pandas as pd
import yfinance as yf

from tw_stock_analyzer.data.finmind_daily_fetcher import FinMindDailyFetcher
from tw_stock_analyzer.data.stock_market_registry import is_twse_listed, to_yahoo_symbol
from tw_stock_analyzer.data.stock_names import resolve_tw_stock_name
from tw_stock_analyzer.data.symbol_utils import to_stock_id
from tw_stock_analyzer.data.twse_fetcher import TwseDailyFetcher


class StockFetcher:
    """擷取台股 OHLCV 歷史資料。"""

    def fetch(
        self,
        symbol: str,
        period: str = "2y",
        interval: str = "1d",
    ) -> pd.DataFrame:
        """
        擷取歷史股價。

        Args:
            symbol: 股票代號（如 2330 或 2330.TW）
            period: 資料期間（1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max）
            interval: K 線週期（1d, 1wk, 1mo）

        Returns:
            含 open, high, low, close, volume 的 DataFrame
        """
        if interval == "1d":
            if self._can_use_twse_daily(symbol):
                try:
                    return TwseDailyFetcher().fetch(symbol, period=period)
                except Exception:
                    pass
            try:
                return FinMindDailyFetcher().fetch(symbol, period=period)
            except Exception:
                pass
            return self._fetch_yfinance(symbol, period=period, interval=interval)
        return self._fetch_yfinance(symbol, period=period, interval=interval)

    @staticmethod
    def _can_use_twse_daily(symbol: str) -> bool:
        stock_id = to_stock_id(symbol)
        if not re.fullmatch(r"\d{4,6}", stock_id):
            return False
        return is_twse_listed(symbol)

    def _fetch_yfinance(
        self,
        symbol: str,
        period: str,
        interval: str,
    ) -> pd.DataFrame:
        ticker = to_yahoo_symbol(symbol)
        yf_log = logging.getLogger("yfinance")
        prev_level = yf_log.level
        yf_log.setLevel(logging.CRITICAL)
        try:
            raw = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
            )
        finally:
            yf_log.setLevel(prev_level)
        if raw.empty:
            raise ValueError(f"無法取得 {ticker} 的資料，請確認代號是否正確。")

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        df = raw.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        required = ["open", "high", "low", "close", "volume"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"資料欄位不完整，缺少：{missing}")

        df = df[required].dropna()
        df.index = pd.to_datetime(df.index)
        df.attrs["symbol"] = ticker
        df.attrs["source"] = "yfinance"
        return df

    def fetch_info(self, symbol: str) -> dict:
        """取得股票基本資訊（名稱、產業等）。"""
        ticker = to_yahoo_symbol(symbol)
        info = yf.Ticker(ticker).info
        yf_name = info.get("longName") or info.get("shortName", "—")
        return {
            "symbol": ticker,
            "name": resolve_tw_stock_name(symbol, yf_name),
            "sector": info.get("sector", "—"),
            "industry": info.get("industry", "—"),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", "TWD"),
        }
