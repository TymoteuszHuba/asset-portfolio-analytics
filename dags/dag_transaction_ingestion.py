"""
Airflow DAG: Transaction Ingestion & Quarantine Pipeline.
Orchestrates CSV parsing, staging storage, two-tier validation, and quarantine isolation.
"""

from datetime import datetime, timedelta
import logging
import os
import glob

from airflow import DAG
from airflow.operators.python import PythonOperator

from src.ingestion.parser import parse_broker_csv
from src.db.repository import (
    register_broker_report,
    save_staging_raw_data,
    save_ingestion_results,
)

logger = logging.getLogger("airflow.task")

INPUT_DIR = "/opt/airflow/input_data"

default_args = {
    "owner": "portfolio_analytics",
    "depends_on_past": False,
    "start_date": datetime(2026, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}


def process_broker_reports(**kwargs):
    """
    Scans the input_data directory, parses CSV reports, executes Tier 1/2 validations,
    and isolates corrupted rows to core.quarantine_records.
    """
    csv_files = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    
    if not csv_files:
        logger.info(f"No CSV files found in {INPUT_DIR}. Ingestion task completed.")
        return "NO_FILES_FOUND"

    processed_summary = []

    for file_path in csv_files:
        file_name = os.path.basename(file_path)
        logger.info(f"Processing broker report: {file_name}")

        # 1. Register report metadata
        file_id = register_broker_report(file_name=file_name, broker_source="GENERIC_CSV")

        # 2. Parse CSV & apply Tier 1 & Tier 2 DQ validations
        valid_events, quarantine_records = parse_broker_csv(file_path, file_id)

        # 3. Save raw staging data
        raw_rows_dict = [
            {"valid_events_count": len(valid_events), "quarantine_count": len(quarantine_records)}
        ]
        save_staging_raw_data(file_name, raw_rows_dict)

        # 4. Save valid events to core.transaction_events & invalid to core.quarantine_records
        final_status = save_ingestion_results(file_id, valid_events, quarantine_records)

        summary_msg = (
            f"File '{file_name}' processed -> Valid: {len(valid_events)}, "
            f"Quarantined: {len(quarantine_records)}, Status: {final_status}"
        )
        logger.info(summary_msg)
        processed_summary.append(summary_msg)

    return "\n".join(processed_summary)


with DAG(
    dag_id="transaction_ingestion_pipeline",
    default_args=default_args,
    description="Fetch Context: Broker CSV parsing, DQ validation, and Quarantine isolation",
    schedule_interval="@daily",
    catchup=False,
    tags=["fetch", "ingestion", "quarantine"],
) as dag:

    ingest_task = PythonOperator(
        task_id="ingest_broker_reports",
        python_callable=process_broker_reports,
    )
