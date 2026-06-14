# Ubiquitous Language: Multi-Asset Portfolio Analytics

Shared domain vocabulary for the project. All future documentation, code and database design must use these terms consistently.

Source: [Business Requirements](../business_requirements.md)



## 1. Actors

* **Investor:** The end user who holds assets at one or more brokers and monitors portfolio performance through the BI dashboard.
    > **Maps to:** BR-01, BR-02, BR-03, US-01, US-02, US-03

* **System administrator:** The operator responsible for pipeline health, API quota and review of quarantined data.
    > **Maps to:** BR-05, FR-05, US-04, US-05



## 2. Portfolio and accounts

* **Broker:** An external institution that executes trades and exports transaction files in a proprietary format.
    > **Maps to:** BR-01, FR-01

* **Broker account:** A single investment account at a given broker. One investor may hold multiple broker accounts.
    > **Maps to:** BR-01

* **Portfolio:** The full set of holdings across all broker accounts. It is a data view — not stored as editable state.
    > **Maps to:** BR-01, BR-02

* **Instrument:** A asset identified by a ticker symbol (e.g. `AAPL`, `VWCE.DE`). Belongs to an asset class and has a native currency.
    > **Maps to:** FR-02, FR-06

* **Ticker:** The unique market identifier of an instrument. Used to join transactions with market prices.
    > **Maps to:** FR-02, FR-07

* **Asset class:** The category of an instrument: `STOCK`, `ETF`, or `FOREX`.
    > **Maps to:** BR-01



## 3. Transactions and ledger

* **Transaction event:** An immutable record of a single financial event (purchase, sale, or dividend). Events are append-only - never updated or deleted.
    > **Maps to:** BR-04, FR-01, US-01

* **Transaction type:** The normalized type of a transaction event. Valid values: `BUY`, `SELL`, `DIVIDEND`.
    > **Maps to:** FR-01

* **Immutable Ledger:** The core storage pattern where all transaction events are kept as an append-only log. Current holdings are calculated by aggregation, not by editing stored state.
    > **Maps to:** BR-04, US-01

* **Position:** The current quantity of an instrument held across all broker accounts, derived from transaction events.
    > **Maps to:** BR-01, BR-02, US-06

* **Cost basis:** The total purchase cost of a position in EUR, including purchase price and fees. Recalculated after a stock split.
    > **Maps to:** BR-04, UC-2, US-06

* **Operational cost:** A fee, commission, or tax attached to a transaction event. Must be preserved for audit and total return calculation.
    > **Maps to:** BR-04, UC-3



## 4. Market data and pricing

* **EOD Price (End-of-Day Price):** The official closing price of an instrument on a trading day, sourced from the FMP API.
    > **Maps to:** FR-02, US-02, UC-1

* **FX rate:** The historical exchange rate between a foreign currency and EUR on a given date (e.g. USD/EUR on 2024-05-15).
    > **Maps to:** FR-03, BR-03, US-01

* **Base currency:** The single reporting currency for all portfolio calculations. Fixed to **EUR** in this system.
    > **Maps to:** BR-03, UC-3

* **LAP (Last Available Price):** On non-trading days (weekends, holidays), the system uses the most recent EOD price from the previous business day. Ensures a gap-free valuation time series.
    > **Maps to:** FR-04, US-03, UC-1

* **Stock split:** A corporate action that changes share count without changing total market value (e.g. 1:4 split). The system adjusts historical prices and position quantities so AUM stays unchanged across the split date.
    > **Maps to:** FR-06, US-06

* **FMP API:** External REST API (Financial Modeling Prep) providing EOD prices, FX rates and stock split data. Free tier limit: 250 requests per day.
    > **Maps to:** FR-02, FR-03, FR-05, FR-06, BR-05


## 5. Data pipeline and quality

* **Broker file:** A broker-generated export file (typically CSV) with raw transaction rows. Column names and formats differ per broker.
    > **Maps to:** FR-01, UC-2

* **Fetch pipeline:** The Airflow ETL process that reads broker files, validates data, normalizes schema and loads valid records into the immutable ledger.
    > **Maps to:** FR-01, FR-07, UC-2

* **Delta load:** Before calling the FMP API, the pipeline checks the latest stored `price_date` and fetches only missing records. Avoids duplicate API calls and protects the daily request limit.
    > **Maps to:** FR-05, BR-05, US-05, UC-1

* **Quarantine record:** A broker-file row that failed validation (e.g. negative quantity, missing ticker). Isolated with a timestamp and error code. The pipeline continues processing valid rows.
    > **Maps to:** FR-07, US-04, UC-2

* **Success with warnings:** The pipeline finished loading valid data, but one or more quarantine records were created. The run does not fail and valid data is not rolled back.
    > **Maps to:** FR-07, US-04, UC-2


## 6. Analytics and reporting

* **AUM (Assets Under Management):** Total market value of all positions on a given date, expressed in EUR.
    > **Maps to:** BR-01, BR-02, US-03, US-06, UC-3

* **Total Return:** Net investment result over a period: current AUM minus capital invested, adjusted for operational costs. Must match actual cash balance within ±0.01 EUR.
    > **Maps to:** BR-04, UC-3

* **Valuation time series:** A continuous daily sequence of AUM values, including non-trading days filled via LAP. Used by the BI dashboard time slider.
    > **Maps to:** BR-02, FR-04, US-03


## 7. Data warehouse layers

* **Staging layer:** The `staging` schema. Raw data as received — parsed CSV rows and FMP API JSON payloads. No business logic applied here.
    > **Maps to:** FR-01, FR-02, UC-1, UC-2

* **Core layer:** The `core` schema. Cleaned, normalized data: transaction events, EOD prices, FX rates, quarantine records.
    > **Maps to:** BR-04, FR-01, FR-06, FR-07

* **Presentation layer:** The `presentation` schema. Pre-computed views for BI: valuation time series, AUM, total return. Queried by Apache Superset.
    > **Maps to:** BR-02, UC-3
