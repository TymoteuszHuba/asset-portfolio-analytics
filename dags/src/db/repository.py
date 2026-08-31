"""
Database persistence repository for DWH transactions and quarantine records.
"""

import json
import os
from typing import List, Dict, Any, Optional
from uuid import UUID

import psycopg2
from psycopg2.extras import execute_values

from src.models.transaction import (
    TransactionEventModel,
    QuarantineRecordModel,
    BrokerReportStatus,
)


def get_db_connection():
    """
    Establishes a connection to the PostgreSQL Data Warehouse.
    Reads connection parameters from environment variables with fallbacks.
    """
    host = os.environ.get("POSTGRES_HOST", "postgres")
    port = int(os.environ.get("POSTGRES_PORT", 5432))
    dbname = os.environ.get("POSTGRES_DB", "portfolio_dwh")
    user = os.environ.get("POSTGRES_USER", "portfolio_user")
    password = os.environ.get("POSTGRES_PASSWORD", "portfolio_password")

    return psycopg2.connect(
        host=host,
        port=port,
        dbname=dbname,
        user=user,
        password=password
    )


def register_broker_report(file_name: str, broker_source: str = "GENERIC_CSV") -> UUID:
    """
    Registers a new broker report file in core.broker_reports and returns its file_id.
    """
    query = """
        INSERT INTO core.broker_reports (file_name, broker_source, status)
        VALUES (%s, %s, %s)
        ON CONFLICT (file_name) 
        DO UPDATE SET upload_timestamp = CURRENT_TIMESTAMP
        RETURNING file_id;
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, (file_name, broker_source, BrokerReportStatus.PROCESSED.value))
            file_id = cur.fetchone()[0]
            conn.commit()
            return file_id
    finally:
        conn.close()


def save_staging_raw_data(file_name: str, raw_rows: List[Dict[str, Any]]) -> None:
    """
    Bulk inserts raw dictionary rows into staging.raw_broker_transactions as JSONB.
    """
    if not raw_rows:
        return

    query = """
        INSERT INTO staging.raw_broker_transactions (file_name, raw_row_data)
        VALUES %s;
    """
    values = [(file_name, json.dumps(row)) for row in raw_rows]
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            execute_values(cur, query, values)
            conn.commit()
    finally:
        conn.close()


def save_ingestion_results(
    file_id: UUID,
    valid_events: List[TransactionEventModel],
    quarantine_records: List[QuarantineRecordModel]
) -> str:
    """
    Persists valid transaction events to core.transaction_events and invalid records to core.quarantine_records.
    Updates core.broker_reports status to SUCCESS_WITH_WARNINGS if errors occurred, otherwise PROCESSED.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # 1. Bulk insert valid transactions
            if valid_events:
                tx_query = """
                    INSERT INTO core.transaction_events (
                        file_id, transaction_date, ticker, type, quantity,
                        unit_price_amount, unit_price_currency,
                        operational_cost_amount, operational_cost_currency
                    ) VALUES %s;
                """
                tx_values = [
                    (
                        str(tx.file_id),
                        tx.transaction_date,
                        tx.ticker,
                        tx.type.value,
                        float(tx.quantity),
                        float(tx.unit_price_amount),
                        tx.unit_price_currency,
                        float(tx.operational_cost_amount),
                        tx.operational_cost_currency
                    )
                    for tx in valid_events
                ]
                execute_values(cur, tx_query, tx_values)

            # 2. Bulk insert quarantine records
            if quarantine_records:
                q_query = """
                    INSERT INTO core.quarantine_records (
                        file_id, raw_line_number, raw_content, validation_error_code
                    ) VALUES %s;
                """
                q_values = [
                    (
                        str(q.file_id),
                        q.raw_line_number,
                        q.raw_content,
                        q.validation_error_code.value
                    )
                    for q in quarantine_records
                ]
                execute_values(cur, q_query, q_values)

            # 3. Determine final status
            final_status = (
                BrokerReportStatus.SUCCESS_WITH_WARNINGS.value
                if quarantine_records
                else BrokerReportStatus.PROCESSED.value
            )

            status_query = """
                UPDATE core.broker_reports
                SET status = %s
                WHERE file_id = %s;
            """
            cur.execute(status_query, (final_status, str(file_id)))

            conn.commit()
            return final_status
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
