# Multi-Asset Portfolio Analytics Platform

An open-source, automated **Portfolio Management & Data Platform** built to import, validate, value and analyze multi-asset investment portfolios (Stocks, ETFs, Forex) into a PostgreSQL database and Apache Superset dashboards.

---

## Real-World Business Problems Solved and End-to-End Pipeline

This platform directly solves 6 key operational challenges in financial data engineering and portfolio management:

1. **Heterogeneous Broker CSV Imports**
   * *Problem:* Different brokers (XTB, Interactive Brokers, Revolut) export transactions with conflicting column names, date formats and structures.
   * *Solution:* Implements a flexible CSV parser with dynamic header and action normalization (`parser.py`) that standardizes raw broker exports without modifying core code.

2. **Data Corruption and Pipeline Resilience (Quarantine Pattern)**
   * *Problem:* A single corrupted row or non-trading record in a massive broker CSV can crash the entire ingestion job.
   * *Solution:* Applies a Two-Tier Data Quality engine (`validators.py`). Valid trades (`BUY`, `SELL`, `DIVIDEND`) flow into the core ledger, while invalid or unparseable entries are safely isolated into `core.quarantine_records` with line numbers and error codes.

3. **API Paywalls and Cost Management (Forex Rates)**
   * *Problem:* Commercial market data providers (e.g. FMP API) restrict historical Forex exchange rates to expensive paid subscription tiers.
   * *Solution:* Catches HTTP 402 subscription errors in `fmp_client.py` and automatically falls back to official European Central Bank daily rates via the 100% free Frankfurter API.

4. **Non-Trading Days Price Gaps (Weekend & Holiday GAP)**
   * *Problem:* Stock exchanges are closed on weekends and holidays, leaving missing price points required for continuous daily portfolio valuation.
   * *Solution:* Executes a high-performance PostgreSQL Last Available Price (LAP) forward-fill algorithm (`lap_interpolator.py`) using window functions to populate non-trading days with Friday's closing prices (`is_interpolated_lap = TRUE`).

5. **Multi-Currency Portfolio Accounting and Profit and Loss Tracking**
   * *Problem:* Tracking holdings acquired in different currencies (USD, EUR) manually makes it difficult to calculate real returns in base currency (PLN/EUR).
   * *Solution:* Implements an automated accounting engine (`valuation_engine.py`) that tracks weighted average cost basis, currency conversions, daily market value (AUM) and both realized and unrealized PnL.

6. **Complex Data Visualization and Executive BI Dashboards**
   * *Problem:* Raw transaction ledgers and financial tables are hard to interpret without visual analytics for executive or personal portfolio tracking.
   * *Solution:* Feeds calculated analytical marts (`presentation.daily_portfolio_metrics`, `presentation.daily_holdings`) directly into **Apache Superset** for interactive visualization of portfolio growth, asset allocation, return rates and PnL trends.

---

## Tech Stack

* **Database**: PostgreSQL 15 (Multi-schema: Staging, Core Ledger, Presentation)
* **Pipeline Orchestration**: Apache Airflow 2.8.1
* **Data Sources & APIs**: Financial Modeling Prep (FMP API) & European Central Bank (Frankfurter API)
* **Core Processing Engine**: Python 3.10 (Pandas, Pydantic, Psycopg2)
* **Dashboards & BI**: Apache Superset 3.0.2
* **Environment**: Docker & Docker Compose
* **Testing**: Pytest

---

## Project and File Structure

```text
multi-asset-porfolio-analytics/
├── docker-compose.yml              # Defines Docker services (PostgreSQL, Airflow, Superset)
├── requirements.txt                # Python package requirements
├── .gitignore                      # Prevents sensitive data and environment files from being uploaded
├── docker/
│   └── postgres/
│       └── init.sql                # SQL script initializing PostgreSQL tables and indexes
├── dags/
│   ├── dag_transaction_ingestion.py# Airflow pipeline for CSV ingestion, validation & quarantine
│   ├── dag_market_data_sync.py     # Airflow pipeline for stock prices, FX rates & gap filling
│   ├── dag_portfolio_valuation.py  # Airflow pipeline for daily portfolio valuation & PnL
│   └── src/
│       ├── models/
│       │   └── transaction.py      # Pydantic models for transactions and error codes
│       ├── validation/
│       │   └── validators.py       # Data quality validation rules (Tier 1 structural, Tier 2 business)
│       ├── ingestion/
│       │   └── parser.py           # CSV report parser with automatic header normalization
│       ├── db/
│       │   └── repository.py       # Database connection and batch SQL save functions
│       ├── market_data/
│       │   ├── fmp_client.py       # API client for stock prices with ECB fallback for FX rates
│       │   ├── sync_engine.py      # Incremental daily market data synchronization
│       │   └── lap_interpolator.py # SQL algorithm for filling weekend/holiday price gaps
│       ├── analytics/
│       │   ├── __init__.py         # Package identifier for analytics module
│       │   └── valuation_engine.py # Portfolio accounting, cost basis, and PnL valuation engine
│       └── tests/
│           ├── test_validators.py      # Unit tests for transaction validation
│           ├── test_market_data.py     # Unit tests for API clients and sync engine
│           ├── test_lap_interpolator.py# Integration test for price gap filling
│           └── test_valuation_engine.py# Unit & integration tests for valuation engine
├── superset/
│   ├── setup_superset.py           # Automated setup: DB connection, datasets, 15 charts & 3-tab dashboard
│   ├── test_superset_setup.py      # Verification tests for Superset configuration (48 assertions)
│   └── dashboards/
│       └── portfolio_360_analytics_export.zip # Complete Dashboard as Code export bundle (ZIP/YAML)
└── input_data/
    └── .gitkeep                    # Folder where user places CSV reports (data files git-ignored)
```

---

## Database Structure (`portfolio_dwh`)

The PostgreSQL database is organized into 3 clear layers:

1. **`staging`**: Stores raw, unparsed JSON data for auditing.
2. **`core`**: Main source of truth storing:
   * `core.transaction_events`: Validated trades (`BUY`, `SELL`, `DIVIDEND`).
   * `core.quarantine_records`: Isolated invalid rows with exact line numbers and error reasons.
   * `core.asset_prices`: Daily stock/ETF closing prices (with gap-filling flags).
   * `core.fx_rates`: Daily currency exchange rates.
   * `core.broker_reports`: Status of processed CSV report files.
3. **`presentation`**: Ready-to-use tables and analytical views for Superset dashboards:
   * `presentation.daily_portfolio_metrics`: Daily total portfolio value, invested cost, returns and PnL.
   * `presentation.daily_holdings`: Daily position details for each stock/ETF held.
   * `presentation.v_quarterly_portfolio_metrics`: Quarterly aggregated valuations, PnL and percentage returns.
   * `presentation.v_quarterly_dividends`: Quarterly cashflow metrics from broker dividend payments.
   * `presentation.v_top_dividend_tickers`: Ranking of stocks generating highest cumulative dividend income.
   * `presentation.v_currency_exposure`: Asset valuation split by currency/regional exposure (USD vs EUR).
   * `presentation.v_latest_holdings`: Latest portfolio holdings snapshot at market-priced valuation date with asset class and regional tagging.
   * `presentation.v_portfolio_drawdown`: Historical peak-to-trough drawdown (%) tracking portfolio risk over time.
   * `presentation.v_dividend_yield_on_cost`: Dividend Yield on Cost (YoC %) per ticker based on historical acquisition cost.
   * `presentation.v_total_return_attribution`: Decomposition of total portfolio profit into capital gains vs cash dividends.

---

## Business Intelligence & Analytics: Portfolio 360 Dashboard

The platform features an automated, enterprise-grade executive dashboard in **Apache Superset** structured across **3 dedicated analytical tabs** with **15 specialized investment visualizations** and **4 native interactive filters**.

```text
Portfolio 360 Analytics Dashboard
├── Tab 1: Executive Overview
│   ├── KPI Cards: Total AUM, Invested Cost Basis, Total Return (EUR), Total Return (%)
│   ├── Portfolio Growth: AUM vs Cost Basis (Area Chart with shaded capital gains)
│   ├── Quarterly PnL Performance (Profit / Loss per calendar quarter)
│   ├── Quarterly Dividend Cashflow (Passive income quarterly distributions)
│   └── Top Dividend Generating Stocks (Historical dividend income leaders)
├── Tab 2: Holdings & Allocation
│   ├── Top 10 Holdings by Market Value (Ranked position sizes in EUR)
│   ├── Top Gainers & Losers (Unrealised PnL ranking across all portfolio stocks)
│   ├── Currency & Regional Exposure (USD vs EUR allocation pie/donut)
│   └── Holdings Detail Table (Full tabular snapshot with sort, search & pagination)
└── Tab 3: Advanced Risk & Performance
    ├── Portfolio Drawdown / Underwater Analysis (% decline from historical all-time peak)
    ├── Dividend Yield on Cost per Ticker (Annualized dividend yield relative to acquisition cost)
    └── Profit Attribution (Decomposition of total returns: Capital Gains vs Cash Dividends)
```

### Native Dashboard Filters (Side Filter Bar)
* **Time Range**: Dynamically filters time-series charts across custom or pre-set horizons (Last Year, Last 3 Years, etc.).
* **Asset Class**: Multi-select filter isolating `Stocks`, `REITs (Real Estate)`, or `ETFs`.
* **Currency & Region**: Filters assets by denomination/geography (`USD (United States)` vs `EUR (Europe)`).
* **Select Ticker(s)**: Multi-select dropdown filtering all asset-level charts to specific companies.

### Key Financial Metrics Explained
* **Total AUM (Assets Under Management)**: Total market value of all held assets converted to base currency (EUR) using daily ECB FX rates.
* **Cost Basis**: Total capital actually invested in acquiring active positions (using weighted average cost basis accounting).
* **Peak-to-Trough Drawdown (%)**: Measures the maximum percentage drop from the portfolio's highest historical valuation. Low drawdown (e.g. -8.14%) demonstrates defensive portfolio resilience.
* **Yield on Cost (YoC %)**: Annual dividend payouts divided by initial purchase cost, illustrating the growing yield of long-held dividend growth stocks.
* **Profit Attribution**: Breaks down overall profits into market price appreciation vs realized cash dividend payments.

---

## How to Run the Project

### 1. Prerequisites
- Docker & Docker Compose installed.

### 2. Environment Configuration
Create a `.env` file in the root folder:
```env
FMP_API_KEY=your_fmp_api_key
POSTGRES_USER=portfolio_user
POSTGRES_PASSWORD=portfolio_password
POSTGRES_DB=portfolio_dwh
```

### 3. Start Containers
```bash
docker compose up -d
```
Access points:
- **Airflow UI**: [http://localhost:8080](http://localhost:8080) (`airflow` / `airflow`)
- **Superset UI**: [http://localhost:8088](http://localhost:8088) (`admin` / `admin`)
- **PostgreSQL**: `localhost:5432` (`portfolio_dwh`)

### 4. Initialize Superset BI Connection, Datasets, Charts & Dashboard

#### Option A: Automated Provisioning via Python (Recommended)
Run the automated setup script to connect Superset to PostgreSQL, register presentation datasets,
create 15 analytical charts and assemble them into the **Portfolio 360 Analytics** dashboard across 3 tabs with 4 native interactive filters (Time Range, Asset Class, Currency & Region, and Ticker Select):
```bash
docker exec -i portfolio_superset python < superset/setup_superset.py
```

Open the dashboard at: [http://localhost:8088/superset/dashboard/1/](http://localhost:8088/superset/dashboard/1/)

#### Option B: Native Dashboard Import (Dashboard as Code)
You can also import the pre-built dashboard bundle directly via the Superset UI:
1. Navigate to **Dashboards** in Superset.
2. Click **Import Dashboards** (top right icon).
3. Select and upload `superset/dashboards/portfolio_360_analytics_export.zip`.

#### Verify the setup
```bash
docker exec -i portfolio_superset python < superset/test_superset_setup.py
```
Expected output: `Results: 48/48 tests passed, 0 failed.`

### 5. Run Tests
To run all automated tests inside the Docker container:
```bash
docker exec -w /opt/airflow/dags portfolio_airflow python -m pytest src/tests/
```

---

## 🔒 Data Privacy & Protection

Your personal financial records and CSV transaction files placed in `input_data/` are automatically ignored by `.gitignore` (`input_data/*`). **They will never be committed or uploaded to GitHub.**
