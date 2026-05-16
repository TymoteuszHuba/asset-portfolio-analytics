# Business Requirements Specification: Multi-Asset Portfolio Management

## 1. Background & Market Problem
Individual investors and small funds (Wealth management / Family Offices) manage capital invested in various asset classes (stocks, ETFs) through many brokers.

Real-world analyses for example of orders from platform like Upwork show that the main business problem is the **lack of a single source of truth**. Each broker provides reports in a different format, time zone, currency. Manually consolidating this data in Excel leads to human error, prevents tracking historical trends and prevents a reliable assessment of risk and reward. 

## 2. Business Requirements
Main target is to define strategic goals of the project from the end user's perspective.

* **BR-01 Wealth Consolidation:** The system must enable centralization of data on all assets held (multiple brokers, multiple accounts) in one place. **Measure of success:** The Stakeholder sees aggregated positions from all accounts on one dashboard and the time needed for manual data compilation drops from several hours to zero (full automation).
* **BR-02 Valuation History:** The system must allow you to check the total portfolio value for any date in the past (historical holdings). **Measure of success:** Selecting any past date on the time slider in Apache Superset generates the correct portfolio valuation (AUM) for that day in under 500ms.
* **BR-03 Single Reporting Currency:** Regardless of the asset's purchase currency (USD, EUR, GBP, etc) the final result must be presented in the investor's base currency (EUR). **Measure of success:** All foreign assets are assigned a value in EUR based on historical exchange rates, enabling accurate calculation of the portfolio's total return without currency disturbs. 
* **BR-04 Audit path:** Every euro (EUR) in the system must be verification. The system must not lose information about commissions, taxes and transaction fees. **Measure of success:** The net profit calculated by the system (Total Return) matches the actual cash and asset balance to the nearest penny (+/- 0.01 EUR) after taking into account all operating costs retrieved from the source files.

## 3. Functional Requirements
