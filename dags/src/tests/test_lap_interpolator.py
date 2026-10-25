"""
Unit tests for LAP (Last Available Price) Forward-Fill Interpolator.
"""

from datetime import date
from decimal import Decimal
import pytest

from src.market_data.lap_interpolator import (
    interpolate_lap_asset_prices,
    interpolate_lap_fx_rates
)
from src.db.repository import get_db_connection


def test_lap_interpolation_asset_prices():
    """
    Verifies that LAP forward-fills weekend gaps (Saturday & Sunday) using Friday's price
    and sets is_interpolated_lap = TRUE.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # Setup clean test state for AAPL_TEST
            cur.execute("DELETE FROM core.asset_prices WHERE ticker = 'AAPL_TEST';")
            
            # Insert Friday 2026-05-15 price (Open trading day)
            cur.execute("""
                INSERT INTO core.asset_prices (ticker, price_date, close_price, currency, is_interpolated_lap)
                VALUES ('AAPL_TEST', '2026-05-15', 150.00, 'USD', FALSE),
                       ('AAPL_TEST', '2026-05-18', 155.00, 'USD', FALSE);
            """)
            conn.commit()

        # Run LAP interpolation algorithm
        inserted_count = interpolate_lap_asset_prices(conn)
        assert inserted_count >= 2  # Saturday 05-16 & Sunday 05-17

        # Verify forward-filled weekend entries
        with conn.cursor() as cur:
            cur.execute("""
                SELECT price_date, close_price, is_interpolated_lap 
                FROM core.asset_prices 
                WHERE ticker = 'AAPL_TEST' 
                ORDER BY price_date;
            """)
            rows = cur.fetchall()

            # Friday 05-15: 150.00 (FALSE)
            assert rows[0][0] == date(2026, 5, 15)
            assert Decimal(str(rows[0][1])) == Decimal("150.00")
            assert rows[0][2] is False

            # Saturday 05-16 (Interpolated weekend): 150.00 (TRUE)
            assert rows[1][0] == date(2026, 5, 16)
            assert Decimal(str(rows[1][1])) == Decimal("150.00")
            assert rows[1][2] is True

            # Sunday 05-17 (Interpolated weekend): 150.00 (TRUE)
            assert rows[2][0] == date(2026, 5, 17)
            assert Decimal(str(rows[2][1])) == Decimal("150.00")
            assert rows[2][2] is True

            # Monday 05-18: 155.00 (FALSE)
            assert rows[3][0] == date(2026, 5, 18)
            assert Decimal(str(rows[3][1])) == Decimal("155.00")
            assert rows[3][2] is False

    finally:
        # Cleanup test data
        with conn.cursor() as cur:
            cur.execute("DELETE FROM core.asset_prices WHERE ticker = 'AAPL_TEST';")
            conn.commit()
        conn.close()
