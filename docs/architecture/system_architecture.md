# System Architecture Specification (C4 Model): Multi-Asset Portfolio Analytics

This document defines the system architecture using the C4 Model methodology (Level 1: System Context and Level 2: Container Diagram).

---

## 1. Level 1: System Context Diagram

The System Context diagram provides a high-level overview of how the Multi-Asset Portfolio Analytics System interacts with user and external services.

```mermaid
graph TB
    Investor(["Investor<br>(End User)"]) -->|Views portfolios & performance| Sys["Multi-Asset Portfolio Analytics System"]
    Admin(["System Administrator"]) -->|Monitors pipeline health & handles quarantine| Sys
    
    Sys -->|Fetches EOD prices & FX rates| FMP["Financial Modeling Prep API<br>(External Financial Service)"]
    Sys -->|Reads transaction reports| Broker["Broker Reports<br>(CSV files in input folder)"]

    style Sys fill:#1182c4,stroke:#0b5784,stroke-width:2px,color:#fff
    style FMP fill:#999999,stroke:#666666,stroke-width:2px,color:#fff
    style Broker fill:#999999,stroke:#666666,stroke-width:2px,color:#fff
    style Investor fill:#08427b,stroke:#052e56,stroke-width:2px,color:#fff
    style Admin fill:#08427b,stroke:#052e56,stroke-width:2px,color:#fff
```

### Actors & External Systems Description
*   **Investor:** The primary user of the system. Looks at aggregated financial KPIs, holdings allocation and AUM performance charts.
*   **System Administrator:** The operator responsible for configuration, managing API keys, reviewing logs and handling quarantined records that failed quality checks.
*   **Financial Modeling Prep (FMP) API:** External source of truth for financial market data. Sells or provides free daily stock/ETF closing prices, split actions and FX exchange rates.
*   **Broker Reports:** Raw transaction files exported from various brokers (e.g., Interactive Brokers, Revolut, XTB) placed into a designated input folder.

---

## 2. Level 2: Container Diagram

The Container diagram zooms into the system boundary, showing the technical building blocks (containers and how they communicate.

```mermaid
graph TB
    subgraph System Boundary ["Multi-Asset Portfolio Analytics System"]
        AirflowWeb["Apache Airflow Webserver<br>(Python / Flask)"]
        AirflowEngine["Apache Airflow Engine<br>(Scheduler & Workers)"]
        
        Postgres["PostgreSQL DWH<br>(Database)"]
        
        Superset["Apache Superset<br>(BI Web Application)"]
        
        InputFolder["Input Directory<br>(Mounted Volume / Local Storage)"]
    end

    Investor -->|Logs in & views dashboards| Superset
    Admin -->|Monitors & triggers DAGs| AirflowWeb
    
    AirflowWeb -->|Read/Write metadata| Postgres
    AirflowEngine -->|Read/Write metadata & DAG execution logs| Postgres
    
    AirflowEngine -->|1. Scans & parses reports| InputFolder
    AirflowEngine -->|2. Queries market data| FMP["FMP API<br>(External)"]
    
    AirflowEngine -->|3. Loads staging & core DWH| Postgres
    AirflowEngine -->|4. Rebuilds presentation schema| Postgres
    
    Superset -->|Queries pre-computed metrics| Postgres

    style Postgres fill:#33a65c,stroke:#22733f,stroke-width:2px,color:#fff
    style Superset fill:#1182c4,stroke:#0b5784,stroke-width:2px,color:#fff
    style AirflowWeb fill:#1182c4,stroke:#0b5784,stroke-width:2px,color:#fff
    style AirflowEngine fill:#1182c4,stroke:#0b5784,stroke-width:2px,color:#fff
    style InputFolder fill:#8c6239,stroke:#5c4025,stroke-width:2px,color:#fff
    style FMP fill:#999999,stroke:#666666,stroke-width:2px,color:#fff
```

### Containers Description

1.  **Apache Superset (BI App):**
    *   *Technology:* Python / Flask / React / Docker container.
    *   *Responsibility:* Renders the interactive portfolio dashboards. Connects only to the `presentation` schema of the database to run high-performance analytical queries.
2.  **Apache Airflow Webserver:**
    *   *Technology:* Python / Flask / Docker container.
    *   *Responsibility:* Administrative UI. Allows the admin to view pipeline execution states, task durations and trigger manual restarts.
3.  **Apache Airflow Engine (Scheduler & Workers):**
    *   *Technology:* Python / Celery / Docker container.
    *   *Responsibility:* Orchestrate and executes the ETL tasks (reading CSV files from the input folder, calling FMP API, validating schema constraints, filtering quarantine rows and calculating daily portfolio valuations).
4.  **PostgreSQL DWH (Database):**
    *   *Technology:* PostgreSQL 15+ / Docker container.
    *   *Responsibility:* Heart of the data layer. Divided into three logical schemas:
        *   `staging`: Transient dat and raw uploads.
        *   `core`: Normalized ledger (`transaction_events`), `quarantine_records`, `asset_prices` and `fx_rates`.
        *   `presentation`: Pre-calculated views optimized for dashboard reporting (`daily_holdings`, `daily_portfolio_metrics`).
5.  **Input Directory:**
    *   *Technology:* Docker shared volume / local filesystem folder.
    *   *Responsibility:* Directory where CSV files are placed by the user or an automated script, acting as the landing zone for the Fetch Context.
