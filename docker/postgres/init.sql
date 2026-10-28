-- Multi-Asset Portfolio Analytics System DWH Initialization Script
-- Schemas: staging, core, presentation
-- ============================================================================

-- 1. Create Required Extensions  and Schemas
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS presentation;


-- 2. STAGING SCHEMA (Transient / Raw Landing)
-- ============================================================================

CREATE TABLE IF NOT EXISTS staging.raw_broker_transactions (
    raw_id       BIGSERIAL PRIMARY KEY,
    file_name    VARCHAR(255) NOT NULL,
    uploaded_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    raw_row_data JSONB NOT NULL
);


-- 3. CORE SCHEMA (Single Source of Truth / Normalized Ledger)
-- ============================================================================

-- Table: core.broker_reports
CREATE TABLE IF NOT EXISTS core.broker_reports (
    file_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_name        VARCHAR(255) UNIQUE NOT NULL,
    broker_source    VARCHAR(100) NOT NULL,
    upload_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status           VARCHAR(50) NOT NULL CHECK (status IN ('PROCESSED', 'SUCCESS_WITH_WARNINGS', 'FAILED'))
);

-- Table: core.quarantine_records
CREATE TABLE IF NOT EXISTS core.quarantine_records (
    record_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id               UUID NOT NULL REFERENCES core.broker_reports(file_id) ON DELETE CASCADE,
    raw_line_number       INTEGER NOT NULL,
    raw_content           TEXT NOT NULL,
    validation_error_code VARCHAR(100) NOT NULL,
    quarantined_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Table: core.transaction_events
CREATE TABLE IF NOT EXISTS core.transaction_events (
    transaction_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id                   UUID REFERENCES core.broker_reports(file_id) ON DELETE SET NULL,
    transaction_date          DATE NOT NULL,
    ticker                    VARCHAR(50) NOT NULL,
    type                      VARCHAR(20) NOT NULL CHECK (type IN ('BUY', 'SELL', 'DIVIDEND')),
    quantity                  NUMERIC(18, 8) NOT NULL CHECK (quantity > 0),
    unit_price_amount         NUMERIC(18, 4) NOT NULL CHECK (unit_price_amount > 0),
    unit_price_currency       VARCHAR(3) NOT NULL,
    operational_cost_amount   NUMERIC(18, 4) NOT NULL DEFAULT 0.0000 CHECK (operational_cost_amount >= 0),
    operational_cost_currency VARCHAR(3) NOT NULL
);

-- Table: core.asset_prices
CREATE TABLE IF NOT EXISTS core.asset_prices (
    ticker              VARCHAR(50) NOT NULL,
    price_date          DATE NOT NULL,
    close_price         NUMERIC(18, 4) NOT NULL CHECK (close_price > 0),
    currency            VARCHAR(3) NOT NULL,
    is_interpolated_lap BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (ticker, price_date)
);

-- Table: core.fx_rates
CREATE TABLE IF NOT EXISTS core.fx_rates (
    base_currency  VARCHAR(3) NOT NULL DEFAULT 'EUR',
    quote_currency VARCHAR(3) NOT NULL,
    rate_date      DATE NOT NULL,
    rate           NUMERIC(18, 6) NOT NULL CHECK (rate > 0),
    PRIMARY KEY (quote_currency, rate_date)
);


-- 4. PRESENTATION SCHEMA (Analytical Marts for Apache Superset)
-- ============================================================================

-- Table: presentation.daily_portfolio_metrics
CREATE TABLE IF NOT EXISTS presentation.daily_portfolio_metrics (
    valuation_date   DATE PRIMARY KEY,
    total_aum_eur    NUMERIC(18, 2) NOT NULL,
    cost_basis_eur   NUMERIC(18, 2) NOT NULL,
    total_return_eur NUMERIC(18, 2) NOT NULL,
    total_return_pct NUMERIC(8, 4) NOT NULL,
    daily_pl_eur     NUMERIC(18, 2) NOT NULL
);

-- Table: presentation.daily_holdings
CREATE TABLE IF NOT EXISTS presentation.daily_holdings (
    valuation_date    DATE NOT NULL,
    ticker            VARCHAR(50) NOT NULL,
    quantity          NUMERIC(18, 8) NOT NULL,
    close_price_eur   NUMERIC(18, 4) NOT NULL,
    market_value_eur  NUMERIC(18, 2) NOT NULL,
    cost_basis_eur    NUMERIC(18, 2) NOT NULL,
    unrealized_pl_eur NUMERIC(18, 2) NOT NULL,
    unrealized_pl_pct NUMERIC(8, 4) NOT NULL,
    PRIMARY KEY (valuation_date, ticker)
);


-- 5. Indexes for Performance Optimization
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_tx_date_ticker ON core.transaction_events(transaction_date, ticker);
CREATE INDEX IF NOT EXISTS idx_quarantine_file ON core.quarantine_records(file_id);
CREATE INDEX IF NOT EXISTS idx_asset_prices_date ON core.asset_prices(price_date);
CREATE INDEX IF NOT EXISTS idx_fx_rates_date ON core.fx_rates(rate_date);

-- View: presentation.v_latest_holdings
CREATE OR REPLACE VIEW presentation.v_latest_holdings AS
SELECT 
    h.valuation_date,
    h.ticker,
    CASE 
        WHEN h.ticker LIKE '%.DE' THEN 'ETFs'
        WHEN h.ticker IN ('O', 'VICI', 'NNN', 'HRZN', 'DLR', 'SPG', 'NLY', 'AMT', 'NYMT') THEN 'REITs'
        ELSE 'Stocks'
    END AS asset_class,
    CASE 
        WHEN h.ticker LIKE '%.DE' THEN 'EUR (Europe)'
        ELSE 'USD (United States)'
    END AS currency_region,
    h.quantity,
    h.close_price_eur,
    h.market_value_eur,
    h.cost_basis_eur,
    h.unrealized_pl_eur,
    h.unrealized_pl_pct
FROM presentation.daily_holdings h
WHERE h.valuation_date = (SELECT MAX(price_date) FROM core.asset_prices);

-- View: presentation.v_currency_exposure
CREATE OR REPLACE VIEW presentation.v_currency_exposure AS
SELECT 
    currency_region,
    ROUND(SUM(market_value_eur), 2) AS total_market_value_eur
FROM presentation.v_latest_holdings
WHERE quantity > 0
GROUP BY 1
ORDER BY total_market_value_eur DESC;


-- View: presentation.v_quarterly_portfolio_metrics
CREATE OR REPLACE VIEW presentation.v_quarterly_portfolio_metrics AS
WITH quarterly_eom AS (
    SELECT 
        DATE_TRUNC('quarter', valuation_date)::DATE AS quarter_start,
        MAX(valuation_date) AS eoq_date,
        SUM(daily_pl_eur) AS quarterly_pl_eur
    FROM presentation.daily_portfolio_metrics
    WHERE valuation_date <= (SELECT MAX(price_date) FROM core.asset_prices)
    GROUP BY DATE_TRUNC('quarter', valuation_date)
)
SELECT 
    q.quarter_start,
    q.eoq_date AS valuation_date,
    TO_CHAR(q.quarter_start, 'YYYY-\"Q\"Q') AS quarter_label,
    p.total_aum_eur,
    p.cost_basis_eur,
    p.total_return_eur,
    ROUND(p.total_return_pct, 2) AS total_return_pct,
    q.quarterly_pl_eur
FROM quarterly_eom q
JOIN presentation.daily_portfolio_metrics p ON p.valuation_date = q.eoq_date
ORDER BY q.quarter_start;

-- View: presentation.v_quarterly_dividends
CREATE OR REPLACE VIEW presentation.v_quarterly_dividends AS
SELECT 
    DATE_TRUNC('quarter', transaction_date)::DATE AS quarter_start,
    TO_CHAR(DATE_TRUNC('quarter', transaction_date), 'YYYY-\"Q\"Q') AS quarter_label,
    ROUND(SUM(quantity * unit_price_amount), 2) AS dividend_amount_eur
FROM core.transaction_events
WHERE type = 'DIVIDEND' AND transaction_date <= '2024-06-30'
GROUP BY DATE_TRUNC('quarter', transaction_date)
ORDER BY quarter_start;

-- View: presentation.v_top_dividend_tickers
CREATE OR REPLACE VIEW presentation.v_top_dividend_tickers AS
SELECT 
    UPPER(ticker) AS ticker,
    ROUND(SUM(quantity * unit_price_amount), 2) AS total_dividends_eur,
    COUNT(*) AS dividend_payout_count
FROM core.transaction_events
WHERE type = 'DIVIDEND'
GROUP BY UPPER(ticker)
ORDER BY total_dividends_eur DESC;

-- View: presentation.v_portfolio_drawdown
CREATE OR REPLACE VIEW presentation.v_portfolio_drawdown AS
WITH daily_peaks AS (
    SELECT 
        valuation_date,
        total_aum_eur,
        MAX(total_aum_eur) OVER (ORDER BY valuation_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS peak_aum_eur
    FROM presentation.daily_portfolio_metrics
    WHERE valuation_date <= (SELECT MAX(price_date) FROM core.asset_prices)
)
SELECT 
    valuation_date,
    total_aum_eur,
    peak_aum_eur,
    ROUND(((total_aum_eur - peak_aum_eur) / NULLIF(peak_aum_eur, 0)) * 100, 2) AS drawdown_pct
FROM daily_peaks
ORDER BY valuation_date;

-- View: presentation.v_dividend_yield_on_cost
CREATE OR REPLACE VIEW presentation.v_dividend_yield_on_cost AS
WITH div_summary AS (
    SELECT 
        UPPER(ticker) AS ticker,
        SUM(quantity * unit_price_amount) AS total_dividends_eur,
        ROUND(SUM(quantity * unit_price_amount) / 4.0, 2) AS annual_dividend_eur
    FROM core.transaction_events
    WHERE type = 'DIVIDEND'
    GROUP BY UPPER(ticker)
)
SELECT 
    h.ticker,
    h.asset_class,
    h.cost_basis_eur,
    h.market_value_eur,
    d.total_dividends_eur,
    d.annual_dividend_eur,
    ROUND((d.annual_dividend_eur / NULLIF(h.cost_basis_eur, 0)) * 100, 2) AS yield_on_cost_pct
FROM presentation.v_latest_holdings h
JOIN div_summary d ON d.ticker = h.ticker
WHERE h.quantity > 0 AND h.cost_basis_eur > 0
ORDER BY yield_on_cost_pct DESC;

-- View: presentation.v_total_return_attribution
CREATE OR REPLACE VIEW presentation.v_total_return_attribution AS
SELECT 
    'Unrealised Capital Gain' AS profit_component,
    ROUND(SUM(unrealized_pl_eur), 2) AS amount_eur
FROM presentation.v_latest_holdings
UNION ALL
SELECT 
    'Cash Dividends Received' AS profit_component,
    ROUND(SUM(quantity * unit_price_amount), 2) AS amount_eur
FROM core.transaction_events
WHERE type = 'DIVIDEND';






