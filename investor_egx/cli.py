from __future__ import annotations

import argparse
import json
from typing import Iterable

from investor_egx.ai_feed import build_ai_feed
from investor_egx.config import load_settings
from investor_egx.db import Database
from investor_egx.pipeline import Pipeline


def _parse_symbols(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    values = [x.strip().upper() for x in raw.split(",") if x.strip()]
    return values or None


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=True))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EGX free-data pipeline CLI")
    parser.add_argument("--db-path", default=None, help="Override DB path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create SQL schema in local database")

    p_tickers = subparsers.add_parser("sync-tickers", help="Sync EGX ticker universe")
    p_tickers.add_argument("--symbols", default=None, help="Optional CSV EGX symbols to filter post-sync view")

    p_daily = subparsers.add_parser("sync-daily", help="Sync daily OHLCV")
    p_daily.add_argument("--symbols", default=None, help="CSV symbols")
    p_daily.add_argument("--start", default="2015-01-01", help="YYYY-MM-DD")

    p_intraday = subparsers.add_parser("sync-intraday", help="Sync intraday OHLCV")
    p_intraday.add_argument("--symbols", default=None, help="CSV symbols")
    p_intraday.add_argument("--interval", default="1m", help="1m,5m,15m,30m,60m")
    p_intraday.add_argument("--days-back", type=int, default=7)

    p_fund = subparsers.add_parser("sync-fundamentals", help="Sync fundamentals")
    p_fund.add_argument("--symbols", default=None, help="CSV symbols")

    p_tech = subparsers.add_parser("sync-technicals", help="Sync technical + analyst sentiment")
    p_tech.add_argument("--symbols", default=None, help="CSV symbols")
    p_tech.add_argument("--timeframe", default="1D")

    p_all = subparsers.add_parser("run-all", help="Run the full pipeline")
    p_all.add_argument("--intraday-interval", default="1m")
    p_all.add_argument("--intraday-days-back", type=int, default=7)

    p_ai = subparsers.add_parser("build-ai-feed", help="Build AI-ready data block for one symbol")
    p_ai.add_argument("--symbol", required=True, help="EGX symbol")
    p_ai.add_argument("--format", default="json", choices=["json", "markdown"])
    p_ai.add_argument("--intraday-rows", type=int, default=360)
    p_ai.add_argument("--daily-rows", type=int, default=180)

    args = parser.parse_args(list(argv) if argv is not None else None)

    settings = load_settings()
    if args.db_path:
        settings = type(settings)(
            db_path=args.db_path,
            request_timeout_sec=settings.request_timeout_sec,
            max_retries=settings.max_retries,
            min_request_interval_sec=settings.min_request_interval_sec,
            user_agent=settings.user_agent,
            alpha_vantage_api_key=settings.alpha_vantage_api_key,
            fmp_api_key=settings.fmp_api_key,
            marketstack_api_key=settings.marketstack_api_key,
            eodhd_api_key=settings.eodhd_api_key,
        )

    db = Database(db_path=settings.db_path)
    pipeline = Pipeline(settings=settings, db=db)

    try:
        if args.command == "init-db":
            db.initialize()
            _print_json({"status": "ok", "db_path": settings.db_path})
            return 0

        if args.command == "sync-tickers":
            result = pipeline.sync_tickers()
            _print_json(result)
            return 0

        if args.command == "sync-daily":
            result = pipeline.sync_daily_prices(
                symbols=_parse_symbols(args.symbols),
                start=args.start,
            )
            _print_json(result)
            return 0

        if args.command == "sync-intraday":
            result = pipeline.sync_intraday_prices(
                symbols=_parse_symbols(args.symbols),
                interval=args.interval,
                days_back=args.days_back,
            )
            _print_json(result)
            return 0

        if args.command == "sync-fundamentals":
            result = pipeline.sync_fundamentals(symbols=_parse_symbols(args.symbols))
            _print_json(result)
            return 0

        if args.command == "sync-technicals":
            result = pipeline.sync_technicals(
                symbols=_parse_symbols(args.symbols),
                timeframe=args.timeframe,
            )
            _print_json(result)
            return 0

        if args.command == "run-all":
            result = pipeline.run_all(
                intraday_interval=args.intraday_interval,
                intraday_days_back=args.intraday_days_back,
            )
            _print_json(result)
            return 0

        if args.command == "build-ai-feed":
            data_block = build_ai_feed(
                db=db,
                egx_symbol=args.symbol.upper(),
                intraday_rows=args.intraday_rows,
                daily_rows=args.daily_rows,
                format_type=args.format,
            )
            print(data_block)
            return 0

        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
