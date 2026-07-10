from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class DBPaths:
    db_path: Path
    schema_path: Path


class Database:
    def __init__(self, db_path: str, schema_path: str = "./sql/schema_sqlite.sql") -> None:
        self.paths = DBPaths(db_path=Path(db_path), schema_path=Path(schema_path))
        self.paths.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.paths.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def transaction(self):
        try:
            yield
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def initialize(self) -> None:
        sql = self.paths.schema_path.read_text(encoding="utf-8")
        self._conn.executescript(sql)
        self._conn.commit()

    def log_pipeline_run_start(self, phase: str, details: dict | None = None) -> int:
        cur = self._conn.execute(
            """
            INSERT INTO pipeline_runs(phase, status, details)
            VALUES (?, 'running', ?)
            """,
            (phase, json.dumps(details or {})),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def log_pipeline_run_finish(self, run_id: int, status: str, details: dict | None = None) -> None:
        self._conn.execute(
            """
            UPDATE pipeline_runs
            SET finished_at = datetime('now'),
                status = ?,
                details = ?
            WHERE run_id = ?
            """,
            (status, json.dumps(details or {}), run_id),
        )
        self._conn.commit()

    def upsert_ticker(self, record: dict) -> int:
        payload = {
            "egx_symbol": record.get("egx_symbol"),
            "isin": record.get("isin"),
            "yahoo_symbol": record.get("yahoo_symbol"),
            "investpy_symbol": record.get("investpy_symbol"),
            "tradingview_symbol": record.get("tradingview_symbol"),
            "company_name": record.get("company_name"),
            "sector": record.get("sector"),
            "industry": record.get("industry"),
            "currency": record.get("currency"),
            "exchange_code": record.get("exchange_code"),
            "is_active": record.get("is_active", 1),
            "first_seen": record.get("first_seen"),
            "last_seen": record.get("last_seen"),
        }
        if not payload["egx_symbol"]:
            raise ValueError("Ticker record must include egx_symbol")
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO tickers(
                    egx_symbol, isin, yahoo_symbol, investpy_symbol, tradingview_symbol,
                    company_name, sector, industry, currency, exchange_code, is_active,
                    first_seen, last_seen, updated_at
                )
                VALUES(
                    :egx_symbol, :isin, :yahoo_symbol, :investpy_symbol, :tradingview_symbol,
                    :company_name, :sector, :industry, COALESCE(:currency, 'EGP'),
                    COALESCE(:exchange_code, 'XCAI'), COALESCE(:is_active, 1),
                    COALESCE(:first_seen, date('now')), COALESCE(:last_seen, date('now')),
                    datetime('now')
                )
                ON CONFLICT(egx_symbol) DO UPDATE SET
                    isin = COALESCE(excluded.isin, tickers.isin),
                    yahoo_symbol = COALESCE(excluded.yahoo_symbol, tickers.yahoo_symbol),
                    investpy_symbol = COALESCE(excluded.investpy_symbol, tickers.investpy_symbol),
                    tradingview_symbol = COALESCE(excluded.tradingview_symbol, tickers.tradingview_symbol),
                    company_name = COALESCE(excluded.company_name, tickers.company_name),
                    sector = COALESCE(excluded.sector, tickers.sector),
                    industry = COALESCE(excluded.industry, tickers.industry),
                    currency = COALESCE(excluded.currency, tickers.currency),
                    exchange_code = COALESCE(excluded.exchange_code, tickers.exchange_code),
                    is_active = COALESCE(excluded.is_active, tickers.is_active),
                    last_seen = COALESCE(excluded.last_seen, tickers.last_seen),
                    updated_at = datetime('now')
                """,
                payload,
            )
            row = self._conn.execute(
                "SELECT ticker_id FROM tickers WHERE egx_symbol = ?",
                (payload["egx_symbol"],),
            ).fetchone()
            if not row:
                raise RuntimeError(f"Failed to upsert ticker {payload['egx_symbol']}")
            return int(row["ticker_id"])

    def upsert_fundamental(self, ticker_id: int, record: dict) -> None:
        payload = dict(record)
        payload["ticker_id"] = ticker_id
        payload["raw_json"] = json.dumps(payload.get("raw_json", {}))
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO fundamentals(
                    ticker_id, as_of_date, pe_ratio, eps, market_cap, dividend_yield,
                    pb_ratio, ps_ratio, roe, roa, debt_to_equity, current_ratio, quick_ratio,
                    revenue_ttm, net_income_ttm, free_cash_flow_ttm, source, raw_json
                ) VALUES(
                    :ticker_id, :as_of_date, :pe_ratio, :eps, :market_cap, :dividend_yield,
                    :pb_ratio, :ps_ratio, :roe, :roa, :debt_to_equity, :current_ratio, :quick_ratio,
                    :revenue_ttm, :net_income_ttm, :free_cash_flow_ttm, :source, :raw_json
                )
                ON CONFLICT(ticker_id, as_of_date) DO UPDATE SET
                    pe_ratio = excluded.pe_ratio,
                    eps = excluded.eps,
                    market_cap = excluded.market_cap,
                    dividend_yield = excluded.dividend_yield,
                    pb_ratio = excluded.pb_ratio,
                    ps_ratio = excluded.ps_ratio,
                    roe = excluded.roe,
                    roa = excluded.roa,
                    debt_to_equity = excluded.debt_to_equity,
                    current_ratio = excluded.current_ratio,
                    quick_ratio = excluded.quick_ratio,
                    revenue_ttm = excluded.revenue_ttm,
                    net_income_ttm = excluded.net_income_ttm,
                    free_cash_flow_ttm = excluded.free_cash_flow_ttm,
                    source = excluded.source,
                    raw_json = excluded.raw_json
                """,
                payload,
            )

    def upsert_technical(self, ticker_id: int, record: dict) -> None:
        payload = dict(record)
        payload["ticker_id"] = ticker_id
        payload["raw_json"] = json.dumps(payload.get("raw_json", {}))
        with self.transaction():
            self._conn.execute(
                """
                INSERT INTO technicals_sentiment(
                    ticker_id, as_of_date, timeframe, technical_recommendation, technical_score,
                    oscillators_recommendation, moving_avg_recommendation,
                    buy_count, neutral_count, sell_count,
                    analyst_recommendation, analyst_buy, analyst_hold, analyst_sell, analyst_total,
                    source, raw_json
                ) VALUES(
                    :ticker_id, :as_of_date, :timeframe, :technical_recommendation, :technical_score,
                    :oscillators_recommendation, :moving_avg_recommendation,
                    :buy_count, :neutral_count, :sell_count,
                    :analyst_recommendation, :analyst_buy, :analyst_hold, :analyst_sell, :analyst_total,
                    :source, :raw_json
                )
                ON CONFLICT(ticker_id, as_of_date, timeframe) DO UPDATE SET
                    technical_recommendation = excluded.technical_recommendation,
                    technical_score = excluded.technical_score,
                    oscillators_recommendation = excluded.oscillators_recommendation,
                    moving_avg_recommendation = excluded.moving_avg_recommendation,
                    buy_count = excluded.buy_count,
                    neutral_count = excluded.neutral_count,
                    sell_count = excluded.sell_count,
                    analyst_recommendation = excluded.analyst_recommendation,
                    analyst_buy = excluded.analyst_buy,
                    analyst_hold = excluded.analyst_hold,
                    analyst_sell = excluded.analyst_sell,
                    analyst_total = excluded.analyst_total,
                    source = excluded.source,
                    raw_json = excluded.raw_json
                """,
                payload,
            )

    def upsert_daily_prices(self, ticker_id: int, rows: Iterable[dict]) -> int:
        payload = []
        for row in rows:
            payload.append(
                (
                    ticker_id,
                    row["trade_date"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("adj_close"),
                    row.get("volume"),
                    row.get("data_source", "unknown"),
                    json.dumps(row.get("raw_json", {})),
                )
            )
        if not payload:
            return 0
        with self.transaction():
            self._conn.executemany(
                """
                INSERT INTO price_daily(
                    ticker_id, trade_date, open, high, low, close, adj_close,
                    volume, data_source, raw_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker_id, trade_date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adj_close = excluded.adj_close,
                    volume = excluded.volume,
                    data_source = excluded.data_source,
                    raw_json = excluded.raw_json
                """,
                payload,
            )
        return len(payload)

    def upsert_intraday_prices(self, ticker_id: int, rows: Iterable[dict]) -> int:
        payload = []
        for row in rows:
            payload.append(
                (
                    ticker_id,
                    row["bar_ts_utc"],
                    row["bar_ts_exchange"],
                    row["interval"],
                    row["open"],
                    row["high"],
                    row["low"],
                    row["close"],
                    row.get("volume"),
                    row.get("vwap"),
                    row.get("is_regular_session"),
                    row.get("data_source", "unknown"),
                    json.dumps(row.get("raw_json", {})),
                )
            )
        if not payload:
            return 0
        with self.transaction():
            self._conn.executemany(
                """
                INSERT INTO price_intraday(
                    ticker_id, bar_ts_utc, bar_ts_exchange, interval, open, high, low,
                    close, volume, vwap, is_regular_session, data_source, raw_json
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker_id, bar_ts_utc, interval) DO UPDATE SET
                    bar_ts_exchange = excluded.bar_ts_exchange,
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    vwap = excluded.vwap,
                    is_regular_session = excluded.is_regular_session,
                    data_source = excluded.data_source,
                    raw_json = excluded.raw_json
                """,
                payload,
            )
        return len(payload)

    def fetch_tickers(self, active_only: bool = True) -> list[sqlite3.Row]:
        if active_only:
            return self._conn.execute(
                "SELECT * FROM tickers WHERE is_active = 1 ORDER BY egx_symbol"
            ).fetchall()
        return self._conn.execute("SELECT * FROM tickers ORDER BY egx_symbol").fetchall()

    def fetch_ticker_by_symbol(self, egx_symbol: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM tickers WHERE egx_symbol = ?",
            (egx_symbol,),
        ).fetchone()

    def build_ai_profile(
        self,
        egx_symbol: str,
        daily_lookback: int = 180,
        intraday_lookback: int = 360,
    ) -> dict:
        ticker = self.fetch_ticker_by_symbol(egx_symbol)
        if not ticker:
            raise KeyError(f"Ticker {egx_symbol} not found")
        ticker_id = int(ticker["ticker_id"])

        fundamentals = self._conn.execute(
            """
            SELECT * FROM fundamentals
            WHERE ticker_id = ?
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            (ticker_id,),
        ).fetchone()

        technicals = self._conn.execute(
            """
            SELECT * FROM technicals_sentiment
            WHERE ticker_id = ?
            ORDER BY as_of_date DESC
            LIMIT 5
            """,
            (ticker_id,),
        ).fetchall()

        daily_prices = self._conn.execute(
            """
            SELECT * FROM price_daily
            WHERE ticker_id = ?
            ORDER BY trade_date DESC
            LIMIT ?
            """,
            (ticker_id, daily_lookback),
        ).fetchall()

        intraday_prices = self._conn.execute(
            """
            SELECT * FROM price_intraday
            WHERE ticker_id = ?
            ORDER BY bar_ts_exchange DESC
            LIMIT ?
            """,
            (ticker_id, intraday_lookback),
        ).fetchall()

        return {
            "ticker": dict(ticker),
            "fundamentals_latest": dict(fundamentals) if fundamentals else None,
            "technicals_recent": [dict(x) for x in technicals],
            "daily_prices_recent": [dict(x) for x in daily_prices],
            "intraday_prices_recent": [dict(x) for x in intraday_prices],
        }
