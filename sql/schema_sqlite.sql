PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tickers (
    ticker_id INTEGER PRIMARY KEY AUTOINCREMENT,
    egx_symbol TEXT NOT NULL UNIQUE,
    isin TEXT UNIQUE,
    yahoo_symbol TEXT,
    investpy_symbol TEXT,
    tradingview_symbol TEXT,
    company_name TEXT,
    sector TEXT,
    industry TEXT,
    currency TEXT NOT NULL DEFAULT 'EGP',
    exchange_code TEXT NOT NULL DEFAULT 'XCAI',
    is_active INTEGER NOT NULL DEFAULT 1,
    first_seen DATE,
    last_seen DATE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tickers_active ON tickers(is_active);
CREATE INDEX IF NOT EXISTS idx_tickers_sector_industry ON tickers(sector, industry);
CREATE INDEX IF NOT EXISTS idx_tickers_yahoo_symbol ON tickers(yahoo_symbol);

CREATE TABLE IF NOT EXISTS fundamentals (
    ticker_id INTEGER NOT NULL,
    as_of_date DATE NOT NULL,
    pe_ratio REAL,
    eps REAL,
    market_cap REAL,
    dividend_yield REAL,
    pb_ratio REAL,
    ps_ratio REAL,
    roe REAL,
    roa REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    quick_ratio REAL,
    revenue_ttm REAL,
    net_income_ttm REAL,
    free_cash_flow_ttm REAL,
    source TEXT NOT NULL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker_id, as_of_date),
    FOREIGN KEY (ticker_id) REFERENCES tickers(ticker_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_date ON fundamentals(as_of_date);
CREATE INDEX IF NOT EXISTS idx_fundamentals_pe ON fundamentals(pe_ratio);

CREATE TABLE IF NOT EXISTS technicals_sentiment (
    ticker_id INTEGER NOT NULL,
    as_of_date DATE NOT NULL,
    timeframe TEXT NOT NULL,
    technical_recommendation TEXT,
    technical_score REAL,
    oscillators_recommendation TEXT,
    moving_avg_recommendation TEXT,
    buy_count INTEGER,
    neutral_count INTEGER,
    sell_count INTEGER,
    analyst_recommendation TEXT,
    analyst_buy INTEGER,
    analyst_hold INTEGER,
    analyst_sell INTEGER,
    analyst_total INTEGER,
    source TEXT NOT NULL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker_id, as_of_date, timeframe),
    FOREIGN KEY (ticker_id) REFERENCES tickers(ticker_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tech_date_timeframe ON technicals_sentiment(as_of_date, timeframe);
CREATE INDEX IF NOT EXISTS idx_tech_reco ON technicals_sentiment(technical_recommendation);
CREATE INDEX IF NOT EXISTS idx_analyst_reco ON technicals_sentiment(analyst_recommendation);

CREATE TABLE IF NOT EXISTS price_daily (
    ticker_id INTEGER NOT NULL,
    trade_date DATE NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    adj_close REAL,
    volume INTEGER,
    data_source TEXT NOT NULL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker_id, trade_date),
    FOREIGN KEY (ticker_id) REFERENCES tickers(ticker_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_daily_trade_date ON price_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_price_daily_ticker_date ON price_daily(ticker_id, trade_date DESC);

CREATE TABLE IF NOT EXISTS price_intraday (
    ticker_id INTEGER NOT NULL,
    bar_ts_utc TEXT NOT NULL,
    bar_ts_exchange TEXT NOT NULL,
    interval TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER,
    vwap REAL,
    is_regular_session INTEGER,
    data_source TEXT NOT NULL,
    raw_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (ticker_id, bar_ts_utc, interval),
    FOREIGN KEY (ticker_id) REFERENCES tickers(ticker_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_price_intraday_lookup ON price_intraday(ticker_id, interval, bar_ts_exchange DESC);
CREATE INDEX IF NOT EXISTS idx_price_intraday_time ON price_intraday(bar_ts_utc DESC);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    phase TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    finished_at TEXT,
    status TEXT NOT NULL,
    details TEXT
);
