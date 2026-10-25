"""
Incremental Sync Engine (Delta Load) for Market Data & FX Rates.
Manages database state checks, active ticker scoping, and API request optimization.
"""

from datetime import date, timedelta
from decimal import Decimal
import logging
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import execute_values

from src.db.repository import get_db_connection
from src.market_data.fmp_client import FMPApiClient, MarketDataAPIError

logger = logging.getLogger("airflow.task")


def get_active_tickers(conn) -> List[str]:
    """
    Retrieves unique list of active tickers present in core.transaction_events.
    """
    query = """
        SELECT DISTINCT UPPER(ticker)
        FROM core.transaction_events
        WHERE ticker IS NOT NULL AND TRIM(ticker) != '';
    """
    with conn.cursor() as cur:
        cur.execute(query)
        rows = cur.fetchall()
        return [r[0] for r in rows]


def get_active_quote_currencies(conn, base_currency: str = "EUR") -> List[str]:
    """
    Retrieves unique list of foreign currencies requiring FX rate conversion to base_currency.
    """
    query = """
        SELECT DISTINCT UPPER(unit_price_currency)
        FROM core.transaction_events
        WHERE unit_price_currency IS NOT NULL 
          AND UPPER(unit_price_currency) != %s;
    """
    with conn.cursor() as cur:
        cur.execute(query, (base_currency.upper(),))
        rows = cur.fetchall()
        return [r[0] for r in rows]


def get_max_asset_price_date(conn, ticker: str) -> Optional[date]:
    """
    Returns MAX(price_date) stored in core.asset_prices for a given ticker.
    """
    query = "SELECT MAX(price_date) FROM core.asset_prices WHERE UPPER(ticker) = %s;"
    with conn.cursor() as cur:
        cur.execute(query, (ticker.upper(),))
        res = cur.fetchone()
        return res[0] if res and res[0] else None


def get_max_fx_rate_date(conn, quote_currency: str, base_currency: str = "EUR") -> Optional[date]:
    """
    Returns MAX(rate_date) stored in core.fx_rates for a given currency pair.
    """
    query = """
        SELECT MAX(rate_date) 
        FROM core.fx_rates 
        WHERE UPPER(quote_currency) = %s AND UPPER(base_currency) = %s;
    """
    with conn.cursor() as cur:
        cur.execute(query, (quote_currency.upper(), base_currency.upper()))
        res = cur.fetchone()
        return res[0] if res and res[0] else None


def save_asset_prices(conn, records: List[Dict[str, Any]]) -> int:
    """
    Massively upserts EOD stock price records into core.asset_prices.
    """
    if not records:
        return 0

    query = """
        INSERT INTO core.asset_prices (ticker, price_date, close_price, currency, is_interpolated_lap)
        VALUES %s
        ON CONFLICT (ticker, price_date)
        DO UPDATE SET 
            close_price = EXCLUDED.close_price,
            currency = EXCLUDED.currency,
            is_interpolated_lap = EXCLUDED.is_interpolated_lap;
    """
    values = [
        (
            rec["ticker"],
            rec["price_date"],
            float(rec["close_price"]),
            rec["currency"],
            rec.get("is_interpolated_lap", False)
        )
        for rec in records
    ]
    with conn.cursor() as cur:
        execute_values(cur, query, values)
        conn.commit()
    return len(records)


def save_fx_rates(conn, records: List[Dict[str, Any]]) -> int:
    """
    Massively upserts FX exchange rate records into core.fx_rates.
    """
    if not records:
        return 0

    query = """
        INSERT INTO core.fx_rates (base_currency, quote_currency, rate_date, rate)
        VALUES %s
        ON CONFLICT (quote_currency, rate_date)
        DO UPDATE SET rate = EXCLUDED.rate;
    """
    values = [
        (
            rec["base_currency"],
            rec["quote_currency"],
            rec["rate_date"],
            float(rec["rate"])
        )
        for rec in records
    ]
    with conn.cursor() as cur:
        execute_values(cur, query, values)
        conn.commit()
    return len(records)


def sync_market_data(
    api_client: Optional[FMPApiClient] = None,
    default_backfill_days: int = 365
) -> Dict[str, int]:
    """
    Executes incremental sync (Delta Load) for active stock prices and FX exchange rates.
    """
    client = api_client or FMPApiClient()
    conn = get_db_connection()

    total_prices_synced = 0
    total_fx_synced = 0
    today = date.today()

    try:
        # 1. Sync Asset Prices for Active Tickers
        active_tickers = get_active_tickers(conn)
        logger.info(f"Active portfolio tickers for market data sync: {active_tickers}")

        for ticker in active_tickers:
            max_date = get_max_asset_price_date(conn, ticker)
            
            if max_date is None:
                start_date = today - timedelta(days=default_backfill_days)
            else:
                start_date = max_date + timedelta(days=1)

            if start_date > today:
                logger.info(f"Ticker '{ticker}' is up to date (Max Date: {max_date}). Skipping API request.")
                continue

            logger.info(f"Fetching EOD prices for '{ticker}' from {start_date} to {today}")
            try:
                fetched_prices = client.fetch_eod_prices(ticker, start_date, today)
                inserted_count = save_asset_prices(conn, fetched_prices)
                total_prices_synced += inserted_count
                logger.info(f"Synced {inserted_count} price records for '{ticker}'.")
            except MarketDataAPIError as err:
                logger.error(f"Failed to fetch market prices for '{ticker}': {err}")

        # 2. Sync FX Rates for Foreign Currencies
        active_currencies = get_active_quote_currencies(conn, base_currency="EUR")
        logger.info(f"Active foreign currencies requiring FX sync: {active_currencies}")

        for quote_curr in active_currencies:
            max_fx_date = get_max_fx_rate_date(conn, quote_curr, base_currency="EUR")
            
            if max_fx_date is None:
                start_date = today - timedelta(days=default_backfill_days)
            else:
                start_date = max_fx_date + timedelta(days=1)

            if start_date > today:
                logger.info(f"FX Pair '{quote_curr}/EUR' is up to date. Skipping API request.")
                continue

            logger.info(f"Fetching FX rates for '{quote_curr}/EUR' from {start_date} to {today}")
            try:
                fetched_fx = client.fetch_fx_rates(quote_curr, "EUR", start_date, today)
                inserted_count = save_fx_rates(conn, fetched_fx)
                total_fx_synced += inserted_count
                logger.info(f"Synced {inserted_count} FX rate records for '{quote_curr}/EUR'.")
            except MarketDataAPIError as err:
                logger.error(f"Failed to fetch FX rates for '{quote_curr}/EUR': {err}")

        return {
            "prices_synced": total_prices_synced,
            "fx_synced": total_fx_synced
        }

    finally:
        conn.close()
