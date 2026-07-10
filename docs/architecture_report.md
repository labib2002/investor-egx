# Ultimate EGX Stock Decision Tool: Free-First Technical Architecture

Date of validation: **February 18, 2026**

This report is written for a production-style personal system optimized for aggressive active trading on EGX with THNDR fee-aware execution logic.

## 0) Executive Architecture

Pipeline layers:

1. **Universe Layer**: Build and refresh EGX tradable symbols.
2. **Market Data Layer**: Daily + intraday OHLCV acquisition with rate-limit controls.
3. **Intelligence Layer**: Fundamentals + technical/analyst sentiment.
4. **Storage Layer**: SQL schema with PK/FK/indexes for fast joins and rolling analytics.
5. **LLM Feed Layer**: Deterministic, token-optimized payload for GPT/Gemini inference.
6. **Trading Ops Layer**: THNDR fee model + aggressive-trading filters.

Project implementation:

- CLI and orchestration: `investor_egx/cli.py`, `investor_egx/pipeline.py`
- Source adapters: `investor_egx/sources/*.py`
- Database: `investor_egx/db.py`, `sql/schema_sqlite.sql`, `sql/schema_postgres.sql`
- AI feed and prompts: `investor_egx/ai_feed.py`, `investor_egx/prompts.py`
- THNDR fee logic: `investor_egx/fees.py`

---

## Phase 1: EGX Ticker Universe and Free Routing

### Recommended free routing strategy (in priority order)

1. **TradingView Screener (Egypt market)**
   - Best practical free source for current active Egypt listings with symbol metadata.
   - In implementation: `TickerUniverseCollector._from_tradingview_screener()`.
2. **investpy country list (`egypt`)**
   - Good backup source for symbol/ISIN lists.
   - In implementation: `TickerUniverseCollector._from_investpy()`.
3. **Yahoo symbol search scanning (`query2` endpoint, CAI exchange filter)**
   - Useful for filling Yahoo-specific symbols (often ISIN-like `EGS...CA`).
   - In implementation: `TickerUniverseCollector._from_yahoo_search()`.

### Why this combination

- EGX official site access can be blocked/unstable for scripted clients from some regions/IPs.
- No single free provider is both stable and complete.
- Multi-source merge with ISIN-first dedupe gives higher coverage and resilience.

### Anti-rate-limit iteration logic

- Global retrying session with `429/5xx` backoff.
- Hard pacing via `RateLimiter` between requests.
- Jittered sleeps to avoid burst signatures.
- Provider fallback order per ticker: `Yahoo -> Investing`.
- Persist partial progress each phase (upsert, no in-memory-only batch risk).

Implementation references:

- `investor_egx/http_utils.py`
- `investor_egx/sources/ticker_universe.py`
- `investor_egx/pipeline.py`

---

## Phase 2: Historical and Intraday Price Action

### Yahoo Finance (`yfinance`) practical answer

Yes, you can request `1m` and `1h` intervals through yfinance endpoints, but with hard constraints:

- Intraday intervals are supported (`1m`, `2m`, `5m`, ...).
- yfinance docs explicitly note: intraday data cannot extend beyond the last 60 days.
- `1m` fetches are additionally constrained in short windows per request (commonly 7 days/request).

In-code handling:

- Chunked download logic in `YahooPriceSource.fetch_intraday()`:
  - `1m` chunks: 7 days
  - other intraday chunks: up to 59 days

### Investing.com (`investpy`) stability and workaround

Observed ecosystem issue:

- `investpy` is brittle against anti-bot changes and can return `403/Too Many Requests`.
- `investpy` historical API itself is day/week/month focused, not native full intraday depth.

Robust workaround:

1. Use `investiny` (actively built around Investing chart endpoints).
2. Add `cloudscraper` session for Cloudflare challenge tolerance and fallback scraping.
3. Resolve symbol -> investing_id once, cache it, then fetch history by ID.

In implementation:

- `investor_egx/sources/prices.py` (`InvestingPriceSource`)
- `investor_egx/sources/technicals.py` (`scrape_analyst_signal_from_page`)

### Free API tier evaluation for EGX (FMP, Alpha Vantage, Marketstack, EODHD)

Short conclusion:

- **Best EGX coverage signal among named APIs:** EODHD (but not unlimited free).
- **Best truly free-first daily/intraday stack in practice:** Yahoo + Investing route with robust scraping controls.

Matrix implemented in `investor_egx/sources/source_matrix.py`.

Practical interpretation:

- **FMP**: free key exists for testing; EGX coverage depth on free is unclear for full active pipeline.
- **Alpha Vantage**: strict free limits (requests/day and requests/min); EGX breadth uncertain as primary source.
- **Marketstack**: free tier is very low volume and intraday is not suitable for non-US free usage.
- **EODHD**: better global market product coverage; free package has low daily call budget.

---

## Phase 3: Fundamentals, Technicals, and Sentiment

### Fundamentals (free-first extraction)

Primary extraction logic:

1. TradingView Screener fields (market cap, P/E, EPS, dividend yield, ratios).
2. Yahoo `Ticker.info` fallback for missing fields.
3. Merge with source precedence (`TradingView -> Yahoo`).

Implementation:

- `investor_egx/sources/fundamentals.py`
- DB table: `fundamentals`

### Technical rating (`tradingview_ta`)

Implemented with:

- `TA_Handler(...).get_analysis()`
- Summary fields: recommendation + buy/neutral/sell counts
- Oscillator and moving-average recommendation breakdown

Implementation:

- `investor_egx/sources/technicals.py` (`_from_tradingview_ta`)

Important caveat:

- `tradingview_ta` repo is archived; keep fallback path via `tradingview-screener`.

### Analyst sentiment (Strong Buy/Hold/Sell)

Primary route (recommended):

- TradingView Screener analyst fields:
  - `recommendation_buy`
  - `recommendation_hold`
  - `recommendation_sell`
  - `recommendation_total`
  - `recommendation_mark`

Fallback route:

- HTML scraping from Investing/TradingView pages with `cloudscraper` and pattern extraction.

Implementation:

- `investor_egx/sources/technicals.py`

---

## Phase 4: Database Architecture (SQL Pipeline)

Exact SQL DDL files:

- SQLite: `sql/schema_sqlite.sql`
- PostgreSQL: `sql/schema_postgres.sql`

Required tables implemented:

1. `tickers` (metadata + sector/industry)
2. `fundamentals` (daily snapshots)
3. `technicals_sentiment` (daily snapshots by timeframe)
4. `price_daily` (historical OHLCV)
5. `price_intraday` (minute/hour bars)

### Key design choices

- Composite PKs on time-series tables prevent duplicates.
- FK cascade from `tickers` keeps referential integrity.
- Secondary indexes optimized for common query patterns:
  - latest by symbol
  - rolling windows by date
  - recommendation screens

### Core CREATE TABLE example (PostgreSQL)

```sql
CREATE TABLE IF NOT EXISTS price_intraday (
    ticker_id BIGINT NOT NULL REFERENCES tickers(ticker_id) ON DELETE CASCADE,
    bar_ts_utc TIMESTAMPTZ NOT NULL,
    bar_ts_exchange TIMESTAMPTZ NOT NULL,
    interval VARCHAR(8) NOT NULL,
    open NUMERIC(18, 6) NOT NULL,
    high NUMERIC(18, 6) NOT NULL,
    low NUMERIC(18, 6) NOT NULL,
    close NUMERIC(18, 6) NOT NULL,
    volume BIGINT,
    vwap NUMERIC(18, 6),
    is_regular_session BOOLEAN,
    data_source VARCHAR(64) NOT NULL,
    raw_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker_id, bar_ts_utc, interval)
);
CREATE INDEX IF NOT EXISTS idx_price_intraday_lookup ON price_intraday(ticker_id, interval, bar_ts_exchange DESC);
```

Full statements are in the SQL files above.

---

## Phase 5: AI Ingestion Feed (Output Layer)

### Implemented function concept

`build_ai_feed(db, egx_symbol, intraday_rows, daily_rows, format_type)` in:

- `investor_egx/ai_feed.py`

It:

1. Queries ticker profile + latest fundamentals + recent technicals/sentiment.
2. Pulls daily and intraday windows.
3. Computes compact derived metrics:
   - 5D/20D/60D returns
   - intraday momentum windows
   - 20D realized volatility
4. Injects THNDR fee model outputs:
   - buy/sell/roundtrip fees
   - break-even move %
5. Emits compact JSON (or markdown).

### System prompt template

Implemented in:

- `investor_egx/prompts.py` (`SYSTEM_PROMPT_TEMPLATE`)

It enforces:

- structured decision class (`BUY_TODAY|WATCHLIST|AVOID_TODAY`)
- confidence score
- tactical plan (entry/stop/targets/RR)
- explicit fee-adjusted viability comment

---

## Aggressive Active-Investor Upgrades Included

1. **Fee drag gating**:
   - Ignore setups with expected edge below THNDR round-trip break-even threshold.
2. **Intraday-first refresh cadence**:
   - `sync-intraday` every 1-5 minutes during session.
   - `sync-fundamentals` and `sync-technicals` daily.
3. **Signal conflict filtering**:
   - Reject high-momentum longs where analyst/technical stacks are deeply negative.
4. **Execution journal extension (next add-on)**:
   - Add a `trades` table with slippage, holding time, and realized R-multiple tracking.
5. **Universe quality scoring (next add-on)**:
   - Assign per-symbol source confidence and staleness score.

---

## Operations Plan (Suggested)

Scheduling:

- 08:45 Africa/Cairo: `sync-tickers`
- 09:00-14:30 every 1-5 min: `sync-intraday`
- End of session: `sync-daily`
- Once daily: `sync-fundamentals`, `sync-technicals`

Command examples:

```bash
python -m investor_egx.cli init-db
python -m investor_egx.cli run-all --intraday-interval 1m --intraday-days-back 7
python -m investor_egx.cli build-ai-feed --symbol COMI --format json
```

---

## Sources

1. yfinance docs (interval support and intraday limit note):  
   https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html
2. yfinance issue discussing 1m request window limit:  
   https://github.com/ranaroussi/yfinance/issues/356
3. investpy stocks API docs (`country='egypt'` support):  
   https://investpy.readthedocs.io/_api/stocks.html
4. investpy issue showing 403 / too many requests failure mode:  
   https://github.com/alvarobartt/investpy/issues/591
5. investiny historical endpoint implementation (`tvc6.investing.com` route):  
   https://github.com/alvarobartt/investiny/blob/main/src/investiny/historical.py
6. cloudscraper README (Cloudflare anti-bot challenge handling):  
   https://github.com/VeNoMouS/cloudscraper
7. tradingview-ta repository (archived status and usage):  
   https://github.com/AnalyzerREST/python-tradingview-ta
8. tradingview-ta usage sample (TA_Handler output):  
   https://raw.githubusercontent.com/AnalyzerREST/python-tradingview-ta/main/README.md
9. tradingview-screener package + docs:  
   https://github.com/shner-elmo/TradingView-Screener
10. tradingview-screener fields, including Egypt market and recommendation fields:  
    https://shner-elmo.github.io/TradingView-Screener/fields/stocks.html
11. Alpha Vantage free-tier limits:  
    https://www.alphavantage.co/premium/
12. Marketstack docs and pricing/free plan constraints:  
    https://marketstack.com/documentation  
    https://marketstack.com/product
13. EODHD pricing and free package details (20 free calls/day):  
    https://eodhd.com/pricing
14. THNDR commission structure support article:  
    https://help.thndr.app/en/support/solutions/articles/151000178492-what-are-my-commission-fees-
