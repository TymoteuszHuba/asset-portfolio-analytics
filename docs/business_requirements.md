# Business Requirements Specification: Multi-Asset Portfolio Management

## 1. Background & Market Problem
Individual investors and small funds (Wealth management / Family Offices) manage capital invested in various asset classes (stocks, ETFs) through many brokers.

Real-world analyses for example of orders from platform like Upwork show that the main business problem is the **lack of a single source of truth**. Each broker provides reports in a different format, time zone, currency. Manually consolidating this data in Excel leads to human error, prevents tracking historical trends and prevents a reliable assessment of risk and reward. 

## 2. Business Requirements
Main target is to define strategic goals of the project from the end user's perspective.

* **BR-01 Wealth consolidation:** The system must enable centralization of data on all assets held (multiple brokers, multiple accounts) in one place. 
    > **Measure of success:** The Stakeholders sees aggregated positions from all accounts on one dashboard and the time needed for manual data compilation drops from several hours to zero (full automation).
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
* **FR-05 Incremental upsert:** Before querying the FMP API, the Airflow data pipeline must check the current database state. Only records newer than max_price in the warehouse are retrieved.
    > **Validation method:** Re-running the Airflow pipeline for the same day does not generate new HTTP requests to the FMP API and does not duplicate rows in the database.
* **FR-06 Adjustment for stocks-splits:** The system must consider the stock split ratio (split) provided by the FMP API so that the historical closing price and position volume are retroactively adjusted.
    > **Validation method:** Verification that after a split (e.g., 1:4), the historical unit purchase cost decreases and the number of shares held increases, maintaining a constant AUM.
* **FR-07 Automatic isolation of incorrect data:** Broker records containing critical errors (missing price, negative volume, unknown ticker) can't stop the Airflow pipeline. Such data must be automatically sent to a separate table (waiting room) for verification.
    > **Validation method:** The integration test loads an intentionally corrupted CSV file. The Airflow pipeline completes with a success status, valid transactions are placed in the core database and corrupt records are isolated in the error table with a description of the cause.