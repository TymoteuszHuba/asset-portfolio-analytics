"""
Airflow DAG: Portfolio Valuation & Presentation Pipeline.
Orchestrates historical daily holdings calculation, cost basis, realized/unrealized PnL
and persistence into the presentation layer for Apache Superset.
"""

from datetime import datetime, timedelta
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.analytics.valuation_engine import run_portfolio_valuation

logger = logging.getLogger("airflow.task")

default_args = {
    "owner": "portfolio_analytics",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def execute_portfolio_valuation(**kwargs):
    """
    Executes portfolio accounting and valuation engine and saves metrics to presentation schema.
    """
    logger.info("Starting Portfolio Valuation and Accounting Engine execution...")
    results = run_portfolio_valuation()
    logger.info(
        f"Portfolio Valuation Execution Complete -> Daily Metrics: {results['daily_metrics_count']}, "
        f"Holdings Records: {results['daily_holdings_count']}"
    )
    return results


with DAG(
    dag_id="portfolio_valuation_pipeline",
    default_args=default_args,
    description="Valuation Context: Calculate daily portfolio metrics, holdings and persist to presentation marts",
    schedule_interval="@daily",
    catchup=False,
    tags=["valuation", "accounting", "pnl", "presentation"],
) as dag:

    valuation_task = PythonOperator(
        task_id="calculate_and_persist_portfolio_valuation",
        python_callable=execute_portfolio_valuation,
    )
