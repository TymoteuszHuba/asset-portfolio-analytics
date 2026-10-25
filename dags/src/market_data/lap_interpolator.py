"""
Last Available Price (LAP) Forward-Fill Interpolator for PostgreSQL DWH.
Fills missing weekend and market holiday gaps in asset prices and FX rates.
"""

import logging
from typing import Dict
import psycopg2

from src.db.repository import get_db_connection

logger = logging.getLogger("airflow.task")


def interpolate_lap_asset_prices(conn) -> int:
    """
    Interpolates missing weekend/holiday dates in core.asset_prices using LAP forward-fill.
    Sets is_interpolated_lap = TRUE for generated non-trading day records.
    Returns count of new interpolated records inserted.
    """
    query = """
        WITH ticker_bounds AS (
            SELECT 
                ticker,
                MIN(price_date) AS min_date,
                MAX(price_date) AS max_date
            FROM core.asset_prices
            GROUP BY ticker
        ),
        calendar AS (
            SELECT 
                b.ticker,
                g.day::date AS price_date
            FROM ticker_bounds b
            CROSS JOIN LATERAL generate_series(b.min_date, b.max_date, INTERVAL '1 day') AS g(day)
        ),
        series_with_groups AS (
            SELECT 
                c.ticker,
                c.price_date,
                p.close_price,
                p.currency,
                COUNT(p.close_price) OVER (PARTITION BY c.ticker ORDER BY c.price_date) AS grp
            FROM calendar c
            LEFT JOIN core.asset_prices p ON c.ticker = p.ticker AND c.price_date = p.price_date
        ),
        filled_series AS (
            SELECT 
                ticker,
                price_date,
                close_price AS actual_price,
                FIRST_VALUE(close_price) OVER (PARTITION BY ticker, grp ORDER BY price_date) AS filled_price,
                FIRST_VALUE(currency) OVER (PARTITION BY ticker, grp ORDER BY price_date) AS filled_currency,
                CASE WHEN close_price IS NULL THEN TRUE ELSE FALSE END AS is_interpolated
            FROM series_with_groups
        )
        INSERT INTO core.asset_prices (ticker, price_date, close_price, currency, is_interpolated_lap)
        SELECT 
            ticker,
            price_date,
            filled_price,
            filled_currency,
            TRUE AS is_interpolated_lap
        FROM filled_series
        WHERE is_interpolated = TRUE AND filled_price IS NOT NULL
        ON CONFLICT (ticker, price_date) DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        inserted_count = cur.rowcount
        conn.commit()
        return inserted_count


def interpolate_lap_fx_rates(conn) -> int:
    """
    Interpolates missing weekend/holiday dates in core.fx_rates using LAP forward-fill.
    Returns count of new interpolated FX rate records inserted.
    """
    query = """
        WITH pair_bounds AS (
            SELECT 
                base_currency,
                quote_currency,
                MIN(rate_date) AS min_date,
                MAX(rate_date) AS max_date
            FROM core.fx_rates
            GROUP BY base_currency, quote_currency
        ),
        calendar AS (
            SELECT 
                b.base_currency,
                b.quote_currency,
                g.day::date AS rate_date
            FROM pair_bounds b
            CROSS JOIN LATERAL generate_series(b.min_date, b.max_date, INTERVAL '1 day') AS g(day)
        ),
        series_with_groups AS (
            SELECT 
                c.base_currency,
                c.quote_currency,
                c.rate_date,
                r.rate,
                COUNT(r.rate) OVER (PARTITION BY c.base_currency, c.quote_currency ORDER BY c.rate_date) AS grp
            FROM calendar c
            LEFT JOIN core.fx_rates r 
                   ON c.base_currency = r.base_currency 
                  AND c.quote_currency = r.quote_currency 
                  AND c.rate_date = r.rate_date
        ),
        filled_series AS (
            SELECT 
                base_currency,
                quote_currency,
                rate_date,
                rate AS actual_rate,
                FIRST_VALUE(rate) OVER (PARTITION BY base_currency, quote_currency, grp ORDER BY rate_date) AS filled_rate,
                CASE WHEN rate IS NULL THEN TRUE ELSE FALSE END AS is_interpolated
            FROM series_with_groups
        )
        INSERT INTO core.fx_rates (base_currency, quote_currency, rate_date, rate)
        SELECT 
            base_currency,
            quote_currency,
            rate_date,
            filled_rate
        FROM filled_series
        WHERE is_interpolated = TRUE AND filled_rate IS NOT NULL
        ON CONFLICT (quote_currency, rate_date) DO NOTHING;
    """
    with conn.cursor() as cur:
        cur.execute(query)
        inserted_count = cur.rowcount
        conn.commit()
        return inserted_count


def run_lap_interpolation() -> Dict[str, int]:
    """
    Executes LAP interpolation for both asset prices and FX rates.
    """
    conn = get_db_connection()
    try:
        prices_interpolated = interpolate_lap_asset_prices(conn)
        fx_interpolated = interpolate_lap_fx_rates(conn)

        logger.info(f"LAP Interpolation complete -> Prices: {prices_interpolated}, FX Rates: {fx_interpolated}")
        return {
            "prices_interpolated": prices_interpolated,
            "fx_interpolated": fx_interpolated
        }
    finally:
        conn.close()
