# Investor EGX Pipeline

A free-data pipeline for the Egyptian Exchange (EGX): ticker universe discovery,
daily OHLCV, fundamentals, technical + analyst sentiment, SQLite persistence, and
a compact AI/LLM-ready decision payload per stock.

Built around free sources (TradingView scanner, Yahoo Finance) with retry/rate-limit
plumbing, idempotent SQL upserts, and a pipeline audit log.

## Honest status (verified 2026-07-10, Windows / Python 3.11)

| Command | Status | Notes |
|---|---|---|
| `init-db` | Works | Creates 6 tables from `sql/schema_sqlite.sql` |
| `sync-tickers` | Works | 343 EGX tickers (289 via TradingView scanner, 55 via Yahoo ISIN search) |
| `sync-daily` | Works | Real OHLCV via yfinance (e.g. COMI: 28 rows for Jun 1 - Jul 9, 2026) |
| `sync-fundamentals` | Works | Rich for TradingView-covered names (P/E, EPS, mcap, ROE, D/E, TTM figures); sparse/NULL for thin micro-caps |
| `sync-technicals` | Works | TradingView TA rating + analyst buy/hold/sell counts |
| `sync-intraday` | Runs, but data is not truly intraday | Yahoo returns ~1 bar/day for EGX regardless of requested interval; see limitations |
| `build-ai-feed` | Works | JSON and markdown formats with returns, realized vol, fundamentals, sentiment, fee math |
| `run-all` | Untested at full scale | Same code paths as the individual commands; a full 343-ticker sweep is slow and rate-limit sensitive |

### Data sources — current reality

- **TradingView scanner API** (`tradingview-screener`): primary source for the ticker
  universe, fundamentals, and analyst recommendation counts. Working.
- **TradingView TA** (`tradingview-ta`): technical ratings (buy/sell/neutral counts,
  oscillator/MA breakdown). Working, but the upstream package is archived.
- **Yahoo Finance** (`yfinance`): daily OHLCV and fallback fundamentals. Working for
  daily bars; unofficial API, rate-limit sensitive, occasional OHLC anomalies for EGX
  (no validation layer is applied).
- **Investing.com** (`investiny`): DEAD. All `tvc*.investing.com` endpoints return
  HTTP 403 (Investing.com shut them down). The code degrades gracefully (the fallback
  simply yields no rows), but no data flows from this source. `cloudscraper` remains
  only for the last-resort HTML label scraper.
- `investpy` universe source: optional import, not installed by default — skipped.

### Known limitations

- **No true intraday data.** For EGX symbols Yahoo serves one bar per day even at
  `1m`/`60m` requests, so `price_intraday` effectively duplicates daily bars. The
  intraday-refresh strategy in `docs/architecture_report.md` is aspirational until a
  real intraday source exists.
- **Two ticker cohorts don't merge.** TradingView rows are keyed by trading symbol
  (`COMI`) and Yahoo-search rows by ISIN (`EGS60121C018`), so the same company can
  appear twice with complementary metadata.
- **Postgres is schema-only.** `sql/schema_postgres.sql` ships the DDL, but
  `db.py` is implemented on `sqlite3` — there is no Postgres connection layer.
- **Silent error handling.** Source adapters swallow exceptions and return empty
  results; a failing source looks identical to an empty market. There is no logging
  and there are no tests.
- Analyst coverage on EGX is thin (single-digit analyst counts for even the largest
  names); treat sentiment fields as weak signals.
- Unknown symbols raise a raw `KeyError` traceback from `build-ai-feed`.

## Quick start

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m investor_egx.cli init-db
python -m investor_egx.cli sync-tickers
python -m investor_egx.cli sync-daily --symbols COMI,HRHO --start 2026-06-01
python -m investor_egx.cli sync-fundamentals --symbols COMI,HRHO
python -m investor_egx.cli sync-technicals --symbols COMI,HRHO --timeframe 1D
python -m investor_egx.cli build-ai-feed --symbol COMI --format markdown
```

Example AI-feed output (markdown mode, real run):

```
## COMI (Commercial International Bank - Egypt (CIB) S.A.E.)
- Last Close: 134.5
- 5D/20D/60D Return (%): 5.66 / 2.63 / None
- 20D Realized Vol (ann., %): 28.27
- Technical: STRONG_BUY | Analyst: STRONG_BUY (buy/hold/sell=4/1/0)
- P/E: 7.10, EPS: 19.26, Dividend Yield: 4.46
- THNDR round-trip fees (EGP 9,953 notional): 22.89 EGP -> 0.23% break-even move
```

## Architecture

```
sources/            adapters (ticker_universe, prices, fundamentals, technicals)
pipeline.py         orchestration: per-phase sync with fallback source order
db.py               SQLite persistence, idempotent upserts, pipeline_runs audit log
ai_feed.py          compact JSON/markdown payload for LLM decision prompts
fees.py             THNDR fee model (brokerage + EGX/MCDR levies, break-even move)
prompts.py          system prompt template for the downstream LLM analyst
sql/                SQLite DDL (used) + Postgres DDL (reference only)
```

Tables: `tickers`, `price_daily`, `price_intraday`, `fundamentals`,
`technicals_sentiment`, `pipeline_runs`. Composite primary keys make every sync
re-runnable without duplicates.

## Configuration

Environment variables (see `.env.example`):

- `INVESTOR_DB_PATH` (default `./data/investor_egx.sqlite3`)
- `INVESTOR_REQUEST_TIMEOUT_SEC`, `INVESTOR_MAX_RETRIES`,
  `INVESTOR_MIN_REQUEST_INTERVAL_SEC`, `INVESTOR_USER_AGENT`
- Optional API keys (`ALPHA_VANTAGE_API_KEY`, `FMP_API_KEY`, `MARKETSTACK_API_KEY`,
  `EODHD_API_KEY`) are read by config but no adapter consumes them yet; the free-tier
  assessment lives in `investor_egx/sources/source_matrix.py`.

## THNDR fee model

`investor_egx/fees.py` implements buy/sell/round-trip fees (0.1% brokerage with
EGP 1.5 minimum, 0.0125% EGX transaction fee, 0.005% EGX/MCDR sell-side fee) and
`break_even_move_pct()` to filter trades whose expected edge is below fee drag.

## Maintenance notes (2026-07-10 verification pass)

Four surgical fixes were applied while verifying against live sources:

1. `sources/prices.py`: flatten yfinance MultiIndex columns (newer yfinance broke
   row normalization, silently yielding 0 price rows).
2. `pipeline.py`: resolve Yahoo symbols as `<EGX_SYMBOL>.CA` when no explicit
   mapping exists (unblocks prices for the TradingView-sourced cohort, e.g. COMI).
3. `sources/fundamentals.py` + `sources/technicals.py`: unmatched tickers no longer
   inherit the first scanner row's data (cross-ticker contamination bug).
4. `sources/technicals.py`: corrected the analyst `recommendation_mark` scale
   (TradingView uses 1 = Strong Buy; the label mapping was inverted).

Disclaimer: educational/personal tooling. Free data sources are unofficial and can
break at any time. Nothing here is investment advice.
