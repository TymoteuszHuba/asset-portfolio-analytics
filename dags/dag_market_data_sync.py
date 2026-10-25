"""
Airflow DAG: Market Data Sync & LAP Forward-Fill Pipeline.
Orchestrates incremental Delta Load fetching of EOD stock prices and FX exchange rates,
followed by PostgreSQL LOCF LAP interpolation for weekend and holiday gaps.
"""

from datetime import datetime, timedelta
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.market_data.sync_engine import sync_market_data
from src.market_data.lap_interpolator import run_lap_interpolation

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


def execute_market_data_delta_sync(**kwargs):
    """
    Executes incremental Delta Load sync for active stock tickers and FX currency pairs.
    """
    logger.info("Starting Market Data Incremental Sync (Delta Load)...")
    results = sync_market_data(default_backfill_days=365)
    logger.info(f"Market Data Sync Results -> Prices Synced: {results['prices_synced']}, FX Rates Synced: {results['fx_synced']}")
    return results


def execute_lap_interpolation(**kwargs):
    """
    Executes PostgreSQL LOCF interpolation for weekend and market holiday price gaps.
    """
    logger.info("Starting Last Available Price (LAP) Weekend/Holiday Interpolation...")
    results = run_lap_interpolation()
    logger.info(f"LAP Interpolation Results -> Prices Interpolated: {results['prices_interpolated']}, FX Interpolated: {results['fx_interpolated']}")
    return results


with DAG(
    dag_id="market_data_sync_pipeline",
    default_args=default_args,
    description="Market Data Context: Incremental Delta Load for EOD prices/FX and LAP forward-fill interpolation",
    schedule_interval="@daily",
    catchup=False,
    tags=["market_data", "fmp", "fx", "lap"],
) as dag:

    sync_delta_task = PythonOperator(
        task_id="sync_market_data_delta",
        python_callable=execute_market_data_delta_sync,
    )

    lap_interpolation_task = PythonOperator(
        task_id="interpolate_lap_gaps",
        python_callable=execute_lap_interpolation,
    )

    # Dependency Pipeline Flow
    sync_delta_task >> lap_interpolation_task
