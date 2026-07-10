CREATE TABLE IF NOT EXISTS tickers (
    ticker_id BIGSERIAL PRIMARY KEY,
    egx_symbol VARCHAR(32) NOT NULL UNIQUE,
    isin VARCHAR(32) UNIQUE,
    yahoo_symbol VARCHAR(64),
    investpy_symbol VARCHAR(64),
    tradingview_symbol VARCHAR(64),
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    currency VARCHAR(8) NOT NULL DEFAULT 'EGP',
    exchange_code VARCHAR(16) NOT NULL DEFAULT 'XCAI',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    first_seen DATE,
    last_seen DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tickers_active ON tickers(is_active);
CREATE INDEX IF NOT EXISTS idx_tickers_sector_industry ON tickers(sector, industry);
CREATE INDEX IF NOT EXISTS idx_tickers_yahoo_symbol ON tickers(yahoo_symbol);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker_id BIGINT NOT NULL REFERENCES tickers(ticker_id) ON DELETE CASCADE,
    as_of_date DATE NOT NULL,
    pe_ratio NUMERIC(18, 6),
    eps NUMERIC(18, 6),
    market_cap NUMERIC(24, 4),
    dividend_yield NUMERIC(18, 6),
    pb_ratio NUMERIC(18, 6),
    ps_ratio NUMERIC(18, 6),
    roe NUMERIC(18, 6),
    roa NUMERIC(18, 6),
    debt_to_equity NUMERIC(18, 6),
    current_ratio NUMERIC(18, 6),
    quick_ratio NUMERIC(18, 6),
    revenue_ttm NUMERIC(24, 4),
    net_income_ttm NUMERIC(24, 4),
    free_cash_flow_ttm NUMERIC(24, 4),
    source VARCHAR(64) NOT NULL,
    raw_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker_id, as_of_date)
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_date ON fundamentals(as_of_date);
CREATE INDEX IF NOT EXISTS idx_fundamentals_pe ON fundamentals(pe_ratio);

CREATE TABLE IF NOT EXISTS technicals_sentiment (
    ticker_id BIGINT NOT NULL REFERENCES tickers(ticker_id) ON DELETE CASCADE,
    as_of_date DATE NOT NULL,
    timeframe VARCHAR(16) NOT NULL,
    technical_recommendation VARCHAR(32),
    technical_score NUMERIC(18, 6),
    oscillators_recommendation VARCHAR(32),
    moving_avg_recommendation VARCHAR(32),
    buy_count INTEGER,
    neutral_count INTEGER,
    sell_count INTEGER,
    analyst_recommendation VARCHAR(32),
    analyst_buy INTEGER,
    analyst_hold INTEGER,
    analyst_sell INTEGER,
    analyst_total INTEGER,
    source VARCHAR(64) NOT NULL,
    raw_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker_id, as_of_date, timeframe)
);

CREATE INDEX IF NOT EXISTS idx_tech_date_timeframe ON technicals_sentiment(as_of_date, timeframe);
CREATE INDEX IF NOT EXISTS idx_tech_reco ON technicals_sentiment(technical_recommendation);
CREATE INDEX IF NOT EXISTS idx_analyst_reco ON technicals_sentiment(analyst_recommendation);

CREATE TABLE IF NOT EXISTS price_daily (
    ticker_id BIGINT NOT NULL REFERENCES tickers(ticker_id) ON DELETE CASCADE,
    trade_date DATE NOT NULL,
    open NUMERIC(18, 6) NOT NULL,
    high NUMERIC(18, 6) NOT NULL,
    low NUMERIC(18, 6) NOT NULL,
    close NUMERIC(18, 6) NOT NULL,
    adj_close NUMERIC(18, 6),
    volume BIGINT,
    data_source VARCHAR(64) NOT NULL,
    raw_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (ticker_id, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_price_daily_trade_date ON price_daily(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_price_daily_ticker_date ON price_daily(ticker_id, trade_date DESC);

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
CREATE INDEX IF NOT EXISTS idx_price_intraday_time ON price_intraday(bar_ts_utc DESC);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id BIGSERIAL PRIMARY KEY,
    phase VARCHAR(64) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL,
    details JSONB
);
