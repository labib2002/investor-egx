from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from investor_egx.config import Settings
from investor_egx.http_utils import RateLimiter, build_retrying_session


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    # yfinance >= 0.2.51 returns MultiIndex columns (field, ticker) even for a
    # single ticker; flatten so row.get("Open") etc. keep working.
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


@dataclass
class YahooPriceSource:
    settings: Settings

    def __post_init__(self) -> None:
        self.limiter = RateLimiter(self.settings.min_request_interval_sec)

    def fetch_daily(
        self,
        yahoo_symbol: str,
        start: str = "2000-01-01",
        end: str | None = None,
    ) -> list[dict]:
        try:
            import yfinance as yf
        except Exception:
            return []
        self.limiter.wait()
        try:
            data = yf.download(
                tickers=yahoo_symbol,
                start=start,
                end=end,
                interval="1d",
                progress=False,
                auto_adjust=False,
                threads=False,
            )
        except Exception:
            return []
        if data is None or data.empty:
            return []
        return self._normalize_daily(_flatten_columns(data), source="yfinance")

    def fetch_intraday(
        self,
        yahoo_symbol: str,
        interval: str = "1m",
        days_back: int = 30,
    ) -> list[dict]:
        try:
            import yfinance as yf
        except Exception:
            return []

        if interval not in {"1m", "2m", "5m", "15m", "30m", "60m"}:
            raise ValueError("Supported intraday intervals: 1m,2m,5m,15m,30m,60m")

        # Yahoo's documented and observed constraints:
        # - 1m requests are typically capped per request window.
        # - Intraday data generally requires sub-60-day windows.
        chunk_days = 7 if interval == "1m" else 59
        capped_days_back = min(days_back, 60 if interval != "1m" else max(days_back, 7))

        end_ts = datetime.now(timezone.utc)
        start_ts = end_ts - timedelta(days=capped_days_back)

        frames: list[pd.DataFrame] = []
        cursor = start_ts
        while cursor < end_ts:
            next_cursor = min(cursor + timedelta(days=chunk_days), end_ts)
            self.limiter.wait()
            try:
                df = yf.download(
                    tickers=yahoo_symbol,
                    start=cursor.strftime("%Y-%m-%d"),
                    end=(next_cursor + timedelta(days=1)).strftime("%Y-%m-%d"),
                    interval=interval,
                    progress=False,
                    auto_adjust=False,
                    prepost=True,
                    threads=False,
                )
            except Exception:
                df = pd.DataFrame()
            if df is not None and not df.empty:
                frames.append(df)
            cursor = next_cursor

        if not frames:
            return []
        merged = pd.concat(frames).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        return self._normalize_intraday(_flatten_columns(merged), interval=interval, source="yfinance")

    def _normalize_daily(self, df: pd.DataFrame, source: str) -> list[dict]:
        rows = []
        for idx, row in df.iterrows():
            trade_date = pd.Timestamp(idx).date().isoformat()
            rows.append(
                {
                    "trade_date": trade_date,
                    "open": _as_float(row.get("Open")),
                    "high": _as_float(row.get("High")),
                    "low": _as_float(row.get("Low")),
                    "close": _as_float(row.get("Close")),
                    "adj_close": _as_float(row.get("Adj Close")),
                    "volume": _as_int(row.get("Volume")),
                    "data_source": source,
                    "raw_json": {
                        "open": _as_float(row.get("Open")),
                        "high": _as_float(row.get("High")),
                        "low": _as_float(row.get("Low")),
                        "close": _as_float(row.get("Close")),
                        "adj_close": _as_float(row.get("Adj Close")),
                        "volume": _as_int(row.get("Volume")),
                    },
                }
            )
        return [
            r
            for r in rows
            if None not in (r["open"], r["high"], r["low"], r["close"]) and r["trade_date"] is not None
        ]

    def _normalize_intraday(self, df: pd.DataFrame, interval: str, source: str) -> list[dict]:
        rows = []
        for idx, row in df.iterrows():
            ts = pd.Timestamp(idx)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            ts_utc = ts.tz_convert("UTC")
            ts_cairo = ts_utc.tz_convert("Africa/Cairo")
            rows.append(
                {
                    "bar_ts_utc": ts_utc.isoformat(),
                    "bar_ts_exchange": ts_cairo.isoformat(),
                    "interval": interval,
                    "open": _as_float(row.get("Open")),
                    "high": _as_float(row.get("High")),
                    "low": _as_float(row.get("Low")),
                    "close": _as_float(row.get("Close")),
                    "volume": _as_int(row.get("Volume")),
                    "vwap": None,
                    "is_regular_session": None,
                    "data_source": source,
                    "raw_json": {
                        "open": _as_float(row.get("Open")),
                        "high": _as_float(row.get("High")),
                        "low": _as_float(row.get("Low")),
                        "close": _as_float(row.get("Close")),
                        "volume": _as_int(row.get("Volume")),
                    },
                }
            )
        return [
            r
            for r in rows
            if None not in (r["open"], r["high"], r["low"], r["close"]) and r["bar_ts_utc"] is not None
        ]


@dataclass
class InvestingPriceSource:
    settings: Settings

    def __post_init__(self) -> None:
        self.session = build_retrying_session(
            user_agent=self.settings.user_agent,
            max_retries=self.settings.max_retries,
        )
        self.limiter = RateLimiter(self.settings.min_request_interval_sec)

    def resolve_investing_id(self, symbol: str) -> int | None:
        try:
            from investiny import search_assets
        except Exception:
            return None
        try:
            results = search_assets(query=symbol, limit=30, type="Stock")
        except Exception:
            return None
        if not results:
            return None
        for item in results:
            if str(item.get("symbol", "")).upper() == symbol.upper():
                try:
                    return int(item["ticker"])
                except Exception:
                    continue
        try:
            return int(results[0]["ticker"])
        except Exception:
            return None

    def fetch_history(
        self,
        investing_id: int,
        from_date: str = "01/01/2000",
        to_date: str | None = None,
        interval: str | int = "D",
    ) -> list[dict]:
        try:
            from investiny import historical_data
        except Exception:
            return []
        self.limiter.wait()
        try:
            results = historical_data(
                investing_id=investing_id,
                from_date=from_date,
                to_date=to_date,
                interval=interval,
            )
        except Exception:
            return []
        if not results:
            return []
        # investiny returns dictionaries with date/open/high/low/close/volume
        if interval in ("D", "W", "M"):
            daily_rows = []
            for row in results:
                daily_rows.append(
                    {
                        "trade_date": str(row.get("date")),
                        "open": _as_float(row.get("open")),
                        "high": _as_float(row.get("high")),
                        "low": _as_float(row.get("low")),
                        "close": _as_float(row.get("close")),
                        "adj_close": None,
                        "volume": _as_int(row.get("volume")),
                        "data_source": "investiny",
                        "raw_json": row,
                    }
                )
            return daily_rows

        intraday_rows = []
        for row in results:
            ts = pd.Timestamp(row.get("date"), tz="Africa/Cairo")
            ts_utc = ts.tz_convert("UTC")
            intraday_rows.append(
                {
                    "bar_ts_utc": ts_utc.isoformat(),
                    "bar_ts_exchange": ts.isoformat(),
                    "interval": f"{interval}m" if isinstance(interval, int) else str(interval),
                    "open": _as_float(row.get("open")),
                    "high": _as_float(row.get("high")),
                    "low": _as_float(row.get("low")),
                    "close": _as_float(row.get("close")),
                    "volume": _as_int(row.get("volume")),
                    "vwap": None,
                    "is_regular_session": None,
                    "data_source": "investiny",
                    "raw_json": row,
                }
            )
        return intraday_rows
