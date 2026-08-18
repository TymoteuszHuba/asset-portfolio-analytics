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
