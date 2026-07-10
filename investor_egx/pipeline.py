from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from investor_egx.config import Settings
from investor_egx.db import Database
from investor_egx.sources.fundamentals import FundamentalsSource
from investor_egx.sources.prices import InvestingPriceSource, YahooPriceSource
from investor_egx.sources.technicals import TechnicalsSentimentSource
from investor_egx.sources.ticker_universe import TickerUniverseCollector


@dataclass
class Pipeline:
    settings: Settings
    db: Database

    def __post_init__(self) -> None:
        self.ticker_collector = TickerUniverseCollector(self.settings)
        self.yahoo_prices = YahooPriceSource(self.settings)
        self.investing_prices = InvestingPriceSource(self.settings)
        self.fundamentals = FundamentalsSource(self.settings)
        self.technicals = TechnicalsSentimentSource(self.settings)

    def sync_tickers(self) -> dict:
        run_id = self.db.log_pipeline_run_start("tickers")
        records = self.ticker_collector.collect()
        inserted = 0
        for rec in records:
            self.db.upsert_ticker(rec)
            inserted += 1
        self.db.log_pipeline_run_finish(
            run_id,
            "success",
            {"records_processed": inserted},
        )
        return {"records_processed": inserted}

    def sync_daily_prices(self, symbols: Iterable[str] | None = None, start: str = "2015-01-01") -> dict:
        run_id = self.db.log_pipeline_run_start("price_daily", {"start": start})
        tickers = self._load_tickers(symbols)
        upserted = 0
        for ticker in tickers:
            yahoo_symbol = self._resolve_yahoo_symbol(ticker)
            rows = []
            if yahoo_symbol:
                rows = self.yahoo_prices.fetch_daily(yahoo_symbol=yahoo_symbol, start=start)
            if not rows:
                investing_id = self._resolve_investing_id(ticker)
                if investing_id:
                    rows = self.investing_prices.fetch_history(
                        investing_id=investing_id,
                        from_date=self._to_us_date(start),
                        interval="D",
                    )
            if rows:
                upserted += self.db.upsert_daily_prices(int(ticker["ticker_id"]), rows)
        self.db.log_pipeline_run_finish(run_id, "success", {"rows_upserted": upserted})
        return {"rows_upserted": upserted}

    def sync_intraday_prices(
        self,
        symbols: Iterable[str] | None = None,
        interval: str = "1m",
        days_back: int = 7,
    ) -> dict:
        run_id = self.db.log_pipeline_run_start(
            "price_intraday",
            {"interval": interval, "days_back": days_back},
        )
        tickers = self._load_tickers(symbols)
        upserted = 0
        for ticker in tickers:
            yahoo_symbol = self._resolve_yahoo_symbol(ticker)
            rows = []
            if yahoo_symbol:
                rows = self.yahoo_prices.fetch_intraday(
                    yahoo_symbol=yahoo_symbol,
                    interval=interval,
                    days_back=days_back,
                )
            if not rows:
                investing_id = self._resolve_investing_id(ticker)
                if investing_id:
                    interval_map = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "60m": 60}
                    invest_interval = interval_map.get(interval, 60)
                    rows = self.investing_prices.fetch_history(
                        investing_id=investing_id,
                        from_date=self._to_us_date((date.today().replace(day=1)).isoformat()),
                        interval=invest_interval,
                    )
            if rows:
                upserted += self.db.upsert_intraday_prices(int(ticker["ticker_id"]), rows)
        self.db.log_pipeline_run_finish(run_id, "success", {"rows_upserted": upserted})
        return {"rows_upserted": upserted}

    def sync_fundamentals(self, symbols: Iterable[str] | None = None) -> dict:
        run_id = self.db.log_pipeline_run_start("fundamentals")
        tickers = self._load_tickers(symbols)
        count = 0
        for ticker in tickers:
            payload = self.fundamentals.fetch(
                egx_symbol=str(ticker["egx_symbol"]),
                yahoo_symbol=self._resolve_yahoo_symbol(ticker),
                tradingview_symbol=ticker["tradingview_symbol"],
            )
            self.db.upsert_fundamental(int(ticker["ticker_id"]), payload)
            count += 1
        self.db.log_pipeline_run_finish(run_id, "success", {"records_processed": count})
        return {"records_processed": count}

    def sync_technicals(self, symbols: Iterable[str] | None = None, timeframe: str = "1D") -> dict:
        run_id = self.db.log_pipeline_run_start("technicals_sentiment", {"timeframe": timeframe})
        tickers = self._load_tickers(symbols)
        count = 0
        for ticker in tickers:
            payload = self.technicals.fetch(
                egx_symbol=str(ticker["egx_symbol"]),
                tradingview_symbol=ticker["tradingview_symbol"],
                timeframe=timeframe,
            )
            self.db.upsert_technical(int(ticker["ticker_id"]), payload)
            count += 1
        self.db.log_pipeline_run_finish(run_id, "success", {"records_processed": count})
        return {"records_processed": count}

    def run_all(self, intraday_interval: str = "1m", intraday_days_back: int = 7) -> dict:
        summary = {}
        summary["tickers"] = self.sync_tickers()
        summary["daily_prices"] = self.sync_daily_prices()
        summary["intraday_prices"] = self.sync_intraday_prices(
            interval=intraday_interval,
            days_back=intraday_days_back,
        )
        summary["fundamentals"] = self.sync_fundamentals()
        summary["technicals"] = self.sync_technicals()
        return summary

    def _load_tickers(self, symbols: Iterable[str] | None) -> list:
        rows = self.db.fetch_tickers(active_only=True)
        if symbols is None:
            return rows
        symbol_set = {s.upper() for s in symbols}
        return [r for r in rows if str(r["egx_symbol"]).upper() in symbol_set]

    def _resolve_yahoo_symbol(self, ticker_row) -> str | None:
        if ticker_row["yahoo_symbol"]:
            return str(ticker_row["yahoo_symbol"])
        if ticker_row["isin"]:
            return f"{ticker_row['isin']}.CA"
        if ticker_row["egx_symbol"]:
            # EGX listings on Yahoo use the Reuters-style code with a .CA
            # suffix (e.g. COMI.CA); missing symbols just return empty data.
            return f"{ticker_row['egx_symbol']}.CA"
        return None

    def _resolve_investing_id(self, ticker_row) -> int | None:
        investpy_symbol = ticker_row["investpy_symbol"] or ticker_row["egx_symbol"]
        if not investpy_symbol:
            return None
        return self.investing_prices.resolve_investing_id(str(investpy_symbol))

    @staticmethod
    def _to_us_date(iso_date: str) -> str:
        # investiny expects m/d/Y.
        y, m, d = iso_date.split("-")
        return f"{int(m)}/{int(d)}/{y}"
