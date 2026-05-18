# Business Requirements Specification: Multi-Asset Portfolio Management

## 1. Background & Market Problem
Individual investors and small funds (Wealth management / Family Offices) manage capital invested in various asset classes (stocks, ETFs) through many brokers.

Real-world analyses for example of orders from platform like Upwork show that the main business problem is the **lack of a single source of truth**. Each broker provides reports in a different format, time zone, currency. Manually consolidating this data in Excel leads to human error, prevents tracking historical trends and prevents a reliable assessment of risk and reward. 

## 2. Business Requirements
Main target is to define strategic goals of the project from the end user's perspective.

* **BR-01 Wealth consolidation:** The system must enable centralization of data on all assets held (multiple brokers, multiple accounts) in one place. 
    > **Measure of success:** The Investor sees aggregated positions from all accounts on one dashboard and the time needed for manual data compilation drops from several hours to zero (full automation).
* **BR-02 Valuation history:** The system must allow you to check the total portfolio value for any date in the past (historical holdings).
    > **Measure of success:** Selecting any past date on the time slider in Apache Superset generates the correct portfolio valuation (AUM) for that day in under 500ms.
* **BR-03 Single reporting currency:** Regardless of the asset's purchase currency (USD, EUR, GBP, etc) the final result must be presented in the investor's base currency (EUR). 
    > **Measure of success:** All foreign assets are assigned a value in EUR based on historical exchange rates, enabling accurate calculation of the portfolio's total return without currency disturbs. 
* **BR-04 Audit path:** Every euro (EUR) in the system must be verification. The system must not lose information about commissions, taxes and transaction fees. 
    > **Measure of success:** The net profit calculated by the system (Total Return) matches the actual cash and asset balance to the nearest penny (+/- 0.01 EUR) after taking into account all operating costs retrieved from the source files.
* **BR-05 API cost optimization:** The system must minimize requests to external financial APIs to stay within the free package limits (250 requests/day).
    > **Measure of success:** The production system never exceeds the daily FMP API limit, regardless of the number of Airflow pipeline restarts.

## 3. Functional Requirements
* **FR-01 Standardization and import of transactions:** The system must process and map heterogeneous source files from different brokers to a single internal standard (BUY, SELL, DIVIDEND). 
    > **Validation method:** The test script verifies that the ETL process correctly unifies different column names (e.g., `Volume` and `Amount`) to the internal `quantity` field.
* **FR-02 Fetching price:** The system must automatically fetch daily historical end-of-day prices for held instruments from the Financial Modeling Prep (FMP) API.
    > **Validation method:** Airflow logs confirm the successful response status (HTTP 200) from the FMP endpoint and verify the presence of the downloaded JSON payload.
* **FR-03 Fx rate download:** The system must automatically download historical exchange rate tables for pairs related to transactions (e.g., USD/EUR, GBP/EUR) from the Forex API section of the FMP.
    > **Validation method:** Database check to ensure that for each transaction in a currency other than EUR, the system can perfectly match the exchange rate from the day.
* **FR-04 Holiday handling:** For days when exchanges are closed (weekends, holidays), the system must automatically assign the assets the last known market price from the previous business day (Last available price - LAP).
    > **Validation method:** A test of the SQL query to the database shows that the date sequence in the portfolio valuation time series has no gaps and the prices for Saturdays and Sundays are identical to the prices from Friday.
* **FR-05 Incremental upsert:** Before querying the FMP API, the Airflow data pipeline must check the current database state. Only records newer than price_date in the warehouse are retrieved.
    > **Validation method:** Re-running the Airflow pipeline for the same day does not generate new HTTP requests to the FMP API and does not duplicate rows in the database.
* **FR-06 Adjustment for stock-splits:** The system must consider the stock splits ratio (split) provided by the FMP API so that the historical closing price and position volume are retroactively adjusted.
    > **Validation method:** Verification that after a split (e.g., 1:4), the historical unit purchase cost decreases and the number of shares held increases, maintaining a constant AUM.
* **FR-07 Automatic isolation of incorrect data:** Broker records containing critical errors (missing price, negative volume, unknown ticker) can't stop the Airflow pipeline. Such data must be automatically sent to a separate table (waiting room) for verification.
    > **Validation method:** The integration test loads an intentionally broken CSV file. The Airflow pipeline completes with a success status, valid transactions are placed in the core database and corrupt records are isolated in the error table with a description of the cause.

## 4. User Stories & Acceptance Criteria 
### US-01: Asset consolidation and single reporting currency
**Maps requirements:** BR-01, BR-03, FR-01, FR-03
> **As an** investor holding assets in multiple currencies (USD, GBP),
> **I want to** upload my multi-broker transaction files into a single system,
> **So that** I can see my entire net worth calculated uniformly in EUR without manual conversions.
#### Acceptance Criteria:
* **Scenario: Successful multi-currency transaction ingestion**
    * **GIVEN** The investor has a stock purchase transaction in USD dated May 15th. The Forex API has retrieved the USD/EUR exchange rate for that day.
    * **WHEN** the ETL pipeline processes this transaction.
    * **THEN** the transaction value is correctly converted to EUR using the correct rate. The resulting record is saved in the general ledger with a precision of 4 decimal places in the database.

### US-02: Automatic stock price download
**Maps requirements:** BR-01, FR-02
> **As an** investor managing a diverse portfolio,
> **I want** the system to automatically fetch daily closing prices for all my active stocks at the end of each trading day,
> **So that** I don't have to manually look up and log market data to know what my assets are worth.
#### Acceptance Criteria:
* **Scenario: Successful End-of-Day price ingestion**
    * **GIVEN** The stock exchange has ended the session for the assets in the investor's portfolio.
    * **WHEN** the orchestrator starts the daily market data download pipeline.
    * **THEN** the system sends a query to the FMP API and retrieves the current closing price. The price is saved in the database with a timestamp reflecting the given trading day.

### US-03: Continuous valuation history and holiday handling
**Maps requirements:** BR-02, FR-04
> **As an** investor analyzing portfolio performance,
> **I want to** see a continuous time-series chart of my asset valuation,
> **So that** I can evaluate my net worth on any given day, including weekends and market holidays.
#### Acceptance Criteria:
* **Scenario: Portfolio valuation on non-trading days**
    * **GIVEN** The stock market was closed on Saturday and Sunday. The last known closing price of the asset on Friday was for example `150.00 EUR`.
    * **WHEN** the system runs the daily AUM calculation process for the entire week. 
    * **THEN** for Saturday and Sunday, the system automatically assigns a price of `150.00 EUR`. The resulting time series in the analytical layer does not contain any gaps in the dates.


### US-04: Automatic data isolation
**Maps requirements:** BR-05, FR-07
> **As a** Data Analyst / System Owner,
> **I want** corrupted or invalid transaction rows to be automatically isolated rather than crashing the entire ingestion process,
> **So that** valid data is successfully processed without interruption, and I can inspect the errors later.
#### Acceptance Criteria:
* **Scenario: Processing a broker file with partial data corruption**
    * **GIVEN** The investor uploads a CSV file containing 98 valid rows and 2 rows with critical errors (e.g., a negative price or missing asset identification code). The target tables are empty.
    * **WHEN** the data ingestion pipeline in the orchestrator is launched. 
    * **THEN** the pipeline exits with a success/warning status (it doesn't crash the entire process). 98 valid rows are sent to the target table in the Core layer. 2 corrupted records are isolated in the error table with a timestamp and the error code.

### US-05: API optimization and incremental
**Maps requirements:** BR-05, FR-05
> **As a** System Administrator utilizing a free API tier,
> **I want** the daily market data pipeline to fetch only missing EOD historical prices,
> **So that** the system remains operational and never exhausts the strict 250-requests/day limit.
#### Acceptance Criteria:
* **Scenario: Incremental upsert**
    * **GIVEN** The database already has fetched and validated stock prices up to day $T-1$.
    * **WHEN** the Airflow pipeline starts automatically for day $T$ (or is restarted manually by the administrator).
    * **THEN** the system queries the FMP API only for records from day $T$. Historical data already in the database is not fetched again from the network, saving the HTTP request limit.

### US-06: Corporate shares (Split) handling
**Maps requirements:** BR-04, FR-06
> **As an** Investor tracking asset performance,
> **I want** the system to automatically adjust historical prices and quantities when a stock split occurs,
> **So that** my historical charts do not show artificial drops in wealth.
#### Acceptance Criteria:
* **Scenario: Processing a stock split event**
    * **GIVEN** Before the split, the investor held 10 shares of company X with a market price of EUR 400.00 each (Total position value = EUR 4,000.00).
    * **WHEN** the company performs a stock split (split) in a 1:4 ratio.
    * **THEN** the system automatically recalculates the position, increasing the number of shares to 40 and reducing the historical price to EUR 100.00. The total value of the position (AUM) before and after the operation remains unchanged and is exactly `4000.00 EUR`.



## 5. Use Cases

### Use Case 1: Automatic, incremental market data update
* **Main actor:** Airflow Scheduler (System)
* **Supporting actors:** Financial Modeling Prep (FMP) API
* **Main condition:** The internal market database contains historical price entries up to day $T-1$.
* **Main scenario:**
    1. The system automatically triggers the data pipeline after the financial markets close (e.g., at 11:00 PM UTC).
    2. The system queries the internal database for the maximum available price date for all active instruments in the portfolio.
    3. The system identifies that data for day $T$ is missing.
    4. The system sends an incremental request (Delta Load) to the financial API for closing prices and FX rates for day $T$.
    5. The financial API returns a valid data payload.
    6. The system performs forward-fill interpolation (LAP) – if day $T$ is a weekday, it saves the price; if it is a weekend/holiday, it copies the closing price from the last available business day (Friday).
    7. The processed data is safely stored in the **Market Price Repository**.
* **Alternative scenario (Data is current):**
    * In step 3, the system discovers that data for day $T$ is already present in the database. The pipeline terminates gracefully without querying the external API, effectively protecting the free plan limits.

---

### Use Case 2: Importing transaction history with data quality support
* **Main actor:** Investor
* **Supporting actors:** Ingestion Pipeline, Storage System
* **Main condition:** The investor uploads a broker-generated transaction file to the dedicated input directory.
* **Main scenario:**
    1. The investor initiates the file import process via the ingestion pipeline.
    2. The system executes the data parser and verifies structural integrity (type validation, missing fields check).
    3. The system unifies schema column names and converts transaction types to the internal standard (e.g., maps local broker terms to generic `BUY`, `SELL`, `DIVIDEND`).
    4. All records pass the quality validation checks.
    5. The system loads the transactions into the transaction history and automatically calculates the adjusted Cost Basis.
* **Alternative scenario (Detection of broken records):**
    * In step 3, the data parser detects that a few rows contain critical anomalies, such as negative volumes or missing currency codes.
    * The system **does not abort** the entire batch processing and does not rollback the operation for the remaining valid transactions.
    * The valid transactions are successfully transferred to the transaction history.
    * The broken records are isolated and extracted into the error log, stamped with an ingestion timestamp and a specific error reason code.
    * The system terminates with a status of "Success with Warnings" and generates an actionable log report for the Investor.

---

### Use Case 3: Multi-currency portfolio performance analysis
* **Main actor:** Investor (End User)
* **Supporting actors:** Analytical/BI Layer, Data Warehouse Analytics Mart
* **Main condition:** The core data warehouse layers have correctly calculated historical positions and mapped all multi-currency transactions to the base currency (EUR).
* **Main scenario:**
    1. The investor logs into the BI analytical panel and opens the main portfolio dashboard.
    2. The investor sets the reporting currency filter to `EUR` and selects a historical timeframe (e.g., "Last 3 Years").
    3. The BI tool transmits an optimized query to the analytical views exposed by the data warehouse.
    4. The data warehouse executes a high-performance join operation combining historical shares from the transaction ledger with asset pricing history and daily FX rates for the selected timeframe.
    5. The dashboard generates a real-time, interactive line chart displaying the Assets Under Management (AUM) trend and the cumulative net return line.
    6. The investor views the true net investment result, which automatically subtracts operational costs (retrieved from transaction fees) and eliminates artificial portfolio fluctuations caused by volatile exchange rates (FX impact isolation).