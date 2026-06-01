"""從 Yahoo Finance 擷取台股歷史資料。"""

from __future__ import annotations

import pandas as pd
import yfinance as yf

from tw_stock_analyzer.data.symbol_utils import normalize_symbol


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
            period: yfinance period（1mo, 6mo, 1y, 2y, 5y, max）
            interval: K 線週期（1d, 1wk, 1mo）

        Returns:
            含 Open, High, Low, Close, Volume 的 DataFrame
        """
        ticker = normalize_symbol(symbol)
        raw = yf.download(
            ticker,
            period=period,
            interval=interval,
            progress=False,
            auto_adjust=True,
        )
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
        return df

    def fetch_info(self, symbol: str) -> dict:
        """取得股票基本資訊（名稱、產業等）。"""
        ticker = normalize_symbol(symbol)
        info = yf.Ticker(ticker).info
        return {
            "symbol": ticker,
            "name": info.get("longName") or info.get("shortName", "—"),
            "sector": info.get("sector", "—"),
            "industry": info.get("industry", "—"),
            "market_cap": info.get("marketCap"),
            "currency": info.get("currency", "TWD"),
        }
