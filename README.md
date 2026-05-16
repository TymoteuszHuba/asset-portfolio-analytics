# Multi-Asset Portfolio Analytics System

Production-grade Data Engineering & Portfolio Management System designed to consolidate investment data across multiple asset classes (Stocks, ETFs, Forex) into a single source of truth.

## Project Overview
This platform automates the End-of-Day (EOD) ingestion of market and currency data, matches it against an immutable transaction ledger, and computes high-fidelity financial KPIs for interactive business intelligence reporting.

### Tech Stack
* **Orchestration:** Apache Airflow
* **Data Warehouse:** PostgreSQL (Multi-schema: Staging, Core Ledger, Analytics Mart)
* **Data Ingestion:** Financial Modeling Prep (FMP) API & Local Data Providers
* **Business Intelligence:** Apache Superset
* **Infrastructure:** Docker & Docker Compose
* **Development Environment:** Cursor AI & Python 3.10+

## Repository Structure
* `config/` - System and environment configurations.
* `dags/` - Apache Airflow DAGs, Python extractors, and transformation SQLs.
* `docker/` - Dockerfiles and container initialization scripts.
* `docs/` - System documentation using the "Documentation as Code" paradigm.
* `superset/` - Dashboard definitions and semantic layer configurations.

## Documentation Index
All technical and business specifications are strictly maintained within the `docs/` repository. Project will follow *Documentation as Code* paradigm.

*For more details please explore the `docs/` diretory to review the full engineering blueprint.*