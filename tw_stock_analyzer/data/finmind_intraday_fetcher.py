"""FinMind 台股分 K（TaiwanStockKBar，Sponsor 會員）。"""

from __future__ import annotations

import pandas as pd

from tw_stock_analyzer.data.finmind_client import get_finmind_client
from tw_stock_analyzer.data.symbol_utils import to_stock_id
from tw_stock_analyzer.data.wantgoo_fetcher import OHLCV_COLS, resample_yfinance_intraday

DATASET = "TaiwanStockKBar"

# 單日一請求，依週期限制回溯交易日數
TRADING_DAYS_BY_TIMEFRAME: dict[str, int] = {
    "1分": 5,
    "5分": 20,
    "15分": 30,
    "30分": 30,
    "60分": 45,
}


class FinMindIntradayFetcher:
    """擷取 FinMind 1 分 K 並重採樣為圖表週期（volume 內部以股數存放）。"""

    def __init__(self) -> None:
        self._client = get_finmind_client()

    def fetch_candlesticks(self, symbol: str, timeframe: str) -> pd.DataFrame:
        if not self._client.has_token:
            raise ValueError("FINMIND_API_TOKEN 未設定")

        stock_id = to_stock_id(symbol)
        day_count = TRADING_DAYS_BY_TIMEFRAME.get(timeframe, 30)
        frames: list[pd.DataFrame] = []
        last_error: str | None = None

        for day in self._recent_trading_day_strings(day_count):
            df, status, err = self._client.get_data_with_status(
                DATASET, stock_id, day, day
            )
            if df is not None and not df.empty:
                frames.append(df)
                continue
            if err and err != "empty":
                last_error = err

        if not frames:
            hint = last_error or "無資料"
            if "free" in (hint or "").lower() or "sponsor" in (hint or "").lower():
                raise ValueError("FinMind 分 K 需 Sponsor 會員權限")
            raise ValueError(f"FinMind 無 {timeframe} 資料：{hint}")

        minute_df = self._to_minute_ohlcv(pd.concat(frames, ignore_index=True))
        if timeframe == "1分":
            out = minute_df
        else:
            out = resample_yfinance_intraday(minute_df, timeframe)

        if out.empty:
            raise ValueError(f"FinMind 無法產生 {timeframe} 資料")
        out.attrs["source"] = "finmind"
        out.attrs["symbol"] = f"{stock_id}.TW"
        return out

    def _recent_trading_day_strings(self, count: int) -> list[str]:
        days: list[str] = []
        cursor = pd.Timestamp.now(tz="Asia/Taipei").normalize().tz_localize(None)
        guard = 0
        while len(days) < count and guard < count * 3:
            if cursor.weekday() < 5:
                days.append(cursor.strftime("%Y-%m-%d"))
            cursor -= pd.Timedelta(days=1)
            guard += 1
        return list(reversed(days))

    def _to_minute_ohlcv(self, raw: pd.DataFrame) -> pd.DataFrame:
        required = {"date", "minute", "open", "high", "low", "close", "volume"}
        missing = required - set(raw.columns)
        if missing:
            raise ValueError(f"FinMind KBar 欄位不足：{sorted(missing)}")

        ts = pd.to_datetime(
            raw["date"].astype(str) + " " + raw["minute"].astype(str),
            errors="coerce",
        )
        # FinMind volume 為張；內部統一以股數存放
        volume_shares = pd.to_numeric(raw["volume"], errors="coerce").fillna(0) * 1000
        out = pd.DataFrame(
            {
                "open": pd.to_numeric(raw["open"], errors="coerce"),
                "high": pd.to_numeric(raw["high"], errors="coerce"),
                "low": pd.to_numeric(raw["low"], errors="coerce"),
                "close": pd.to_numeric(raw["close"], errors="coerce"),
                "volume": volume_shares,
            },
            index=ts,
        )
        out = out.dropna(subset=["close"]).sort_index()
        out = out[~out.index.duplicated(keep="last")]
        return out[list(OHLCV_COLS)]
