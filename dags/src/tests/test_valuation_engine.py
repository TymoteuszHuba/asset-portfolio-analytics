"""
Unit and integration tests for Valuation & Accounting Engine.
Verifies weighted average cost basis, realized/unrealized PnL,
multi-currency FX conversions and persistence to presentation marts.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest

from src.analytics.valuation_engine import ValuationEngine, run_portfolio_valuation
from src.db.repository import get_db_connection


def test_weighted_average_cost_basis_and_unrealized_pnl():
    """
    Verifies that consecutive BUY transactions calculate weighted average cost basis
    and accurate unrealized PnL based on market prices.
    """
    d1 = date.today() - timedelta(days=2)
    d2 = date.today() - timedelta(days=1)
    d3 = date.today()

    mock_txns = [
        {
            "transaction_date": d1,
            "ticker": "AAPL",
            "type": "BUY",
            "quantity": Decimal("10.0"),
            "unit_price_amount": Decimal("100.00"),
            "unit_price_currency": "EUR",
            "operational_cost_amount": Decimal("0.00"),
            "operational_cost_currency": "EUR",
        },
        {
            "transaction_date": d2,
            "ticker": "AAPL",
            "type": "BUY",
            "quantity": Decimal("10.0"),
            "unit_price_amount": Decimal("150.00"),
            "unit_price_currency": "EUR",
            "operational_cost_amount": Decimal("0.00"),
            "operational_cost_currency": "EUR",
        },
    ]

    mock_prices = [
        {"price_date": d1, "ticker": "AAPL", "close_price": Decimal("105.00"), "currency": "EUR"},
        {"price_date": d2, "ticker": "AAPL", "close_price": Decimal("160.00"), "currency": "EUR"},
        {"price_date": d3, "ticker": "AAPL", "close_price": Decimal("160.00"), "currency": "EUR"},
    ]

    mock_fx = []

    engine = ValuationEngine()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.side_effect = [mock_txns, mock_prices, mock_fx]

    with patch.object(engine, "_get_connection", return_value=mock_conn):
        metrics, holdings = engine.calculate_portfolio_valuation()

        # Day 2 holdings check:
        # Total qty = 20, Total Cost Basis = 1000 + 1500 = 2500 EUR. Avg cost = 125 EUR.
        # Market Price = 160 EUR -> Market Value = 20 * 160 = 3200 EUR.
        # Unrealized PnL = 3200 - 2500 = +700 EUR (+28.00%).
        d2_holding = next(h for h in holdings if h["valuation_date"] == d2 and h["ticker"] == "AAPL")
        assert d2_holding["quantity"] == Decimal("20.00000000")
        assert d2_holding["cost_basis_eur"] == Decimal("2500.00")
        assert d2_holding["market_value_eur"] == Decimal("3200.00")
        assert d2_holding["unrealized_pl_eur"] == Decimal("700.00")
        assert d2_holding["unrealized_pl_pct"] == Decimal("28.0000")


def test_realized_pnl_on_partial_sell():
    """
    Verifies that a partial SELL transaction calculates realized PnL correctly
    and reduces quantity and cost basis proportionally.
    """
    d1 = date.today() - timedelta(days=2)
    d2 = date.today() - timedelta(days=1)

    mock_txns = [
        {
            "transaction_date": d1,
            "ticker": "MSFT",
            "type": "BUY",
            "quantity": Decimal("10.0"),
            "unit_price_amount": Decimal("100.00"),
            "unit_price_currency": "EUR",
            "operational_cost_amount": Decimal("0.00"),
            "operational_cost_currency": "EUR",
        },
        {
            "transaction_date": d2,
            "ticker": "MSFT",
            "type": "SELL",
            "quantity": Decimal("4.0"),
            "unit_price_amount": Decimal("150.00"),
            "unit_price_currency": "EUR",
            "operational_cost_amount": Decimal("10.00"),  # 10 EUR fee
            "operational_cost_currency": "EUR",
        },
    ]

    mock_prices = [
        {"price_date": d1, "ticker": "MSFT", "close_price": Decimal("100.00"), "currency": "EUR"},
        {"price_date": d2, "ticker": "MSFT", "close_price": Decimal("150.00"), "currency": "EUR"},
    ]

    engine = ValuationEngine()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.side_effect = [mock_txns, mock_prices, []]

    with patch.object(engine, "_get_connection", return_value=mock_conn):
        metrics, holdings = engine.calculate_portfolio_valuation()

        # Proceeds = (4 * 150) - 10 = 590 EUR.
        # Cost portion = 4 * 100 = 400 EUR.
        # Realized PnL = 590 - 400 = +190 EUR.
        # Remaining qty = 6, remaining cost basis = 1000 - 400 = 600 EUR.
        d2_holding = next(h for h in holdings if h["valuation_date"] == d2 and h["ticker"] == "MSFT")
        assert d2_holding["quantity"] == Decimal("6.00000000")
        assert d2_holding["cost_basis_eur"] == Decimal("600.00")
        assert d2_holding["market_value_eur"] == Decimal("900.00")


def test_multi_currency_fx_conversion():
    """
    Verifies that foreign currency (USD) transactions and prices are correctly
    converted to base currency (EUR) using core.fx_rates.
    """
    d1 = date.today() - timedelta(days=1)

    mock_txns = [
        {
            "transaction_date": d1,
            "ticker": "NVDA",
            "type": "BUY",
            "quantity": Decimal("5.0"),
            "unit_price_amount": Decimal("200.00"),  # 200 USD
            "unit_price_currency": "USD",
            "operational_cost_amount": Decimal("0.00"),
            "operational_cost_currency": "USD",
        }
    ]

    mock_prices = [
        {"price_date": d1, "ticker": "NVDA", "close_price": Decimal("220.00"), "currency": "USD"}
    ]

    # FX rate: 1 USD = 0.92 EUR
    mock_fx = [
        {"rate_date": d1, "base_currency": "EUR", "quote_currency": "USD", "rate": Decimal("0.920000")}
    ]

    engine = ValuationEngine()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.side_effect = [mock_txns, mock_prices, mock_fx]

    with patch.object(engine, "_get_connection", return_value=mock_conn):
        metrics, holdings = engine.calculate_portfolio_valuation()

        # Purchase cost in EUR: 5 * 200 USD * 0.92 = 920.00 EUR
        # Market Value in EUR: 5 * 220 USD * 0.92 = 1012.00 EUR
        # Unrealized PnL: 1012 - 920 = +92.00 EUR (+10.00%)
        d1_holding = next(h for h in holdings if h["valuation_date"] == d1 and h["ticker"] == "NVDA")
        assert d1_holding["cost_basis_eur"] == Decimal("920.00")
        assert d1_holding["market_value_eur"] == Decimal("1012.00")
        assert d1_holding["unrealized_pl_eur"] == Decimal("92.00")
        assert d1_holding["unrealized_pl_pct"] == Decimal("10.0000")


def test_full_position_close_reset():
    """
    Verifies that selling 100% of an asset resets quantity and cost basis to zero
    without raising zero-division errors.
    """
    d1 = date.today() - timedelta(days=2)
    d2 = date.today() - timedelta(days=1)

    mock_txns = [
        {
            "transaction_date": d1,
            "ticker": "TSLA_TEST",
            "type": "BUY",
            "quantity": Decimal("10.0"),
            "unit_price_amount": Decimal("200.00"),
            "unit_price_currency": "EUR",
            "operational_cost_amount": Decimal("0.00"),
            "operational_cost_currency": "EUR",
        },
        {
            "transaction_date": d2,
            "ticker": "TSLA_TEST",
            "type": "SELL",
            "quantity": Decimal("10.0"),  # Full exit
            "unit_price_amount": Decimal("250.00"),
            "unit_price_currency": "EUR",
            "operational_cost_amount": Decimal("0.00"),
            "operational_cost_currency": "EUR",
        },
    ]

    mock_prices = [
        {"price_date": d1, "ticker": "TSLA_TEST", "close_price": Decimal("200.00"), "currency": "EUR"},
        {"price_date": d2, "ticker": "TSLA_TEST", "close_price": Decimal("250.00"), "currency": "EUR"},
    ]

    engine = ValuationEngine()

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_cur.fetchall.side_effect = [mock_txns, mock_prices, []]

    with patch.object(engine, "_get_connection", return_value=mock_conn):
        metrics, holdings = engine.calculate_portfolio_valuation()

        # On d2, since quantity is 0, TSLA_TEST should not appear in active daily holdings
        d2_tsla_holdings = [h for h in holdings if h["valuation_date"] == d2 and h["ticker"] == "TSLA_TEST"]
        assert len(d2_tsla_holdings) == 0


def test_run_portfolio_valuation_integration():
    """
    Integration test verifying that run_portfolio_valuation runs against
    the database and populates presentation schema tables.
    """
    result = run_portfolio_valuation()
    assert result["daily_metrics_count"] > 0
    assert result["daily_holdings_count"] > 0

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM presentation.daily_portfolio_metrics;")
            metrics_count = cur.fetchone()[0]
            assert metrics_count >= result["daily_metrics_count"]

            cur.execute("SELECT COUNT(*) FROM presentation.daily_holdings;")
            holdings_count = cur.fetchone()[0]
            assert holdings_count >= result["daily_holdings_count"]

            cur.execute("""
                SELECT total_aum_eur, cost_basis_eur
                FROM presentation.daily_portfolio_metrics
                ORDER BY valuation_date DESC
                LIMIT 1;
            """)
            latest_row = cur.fetchone()
            assert latest_row is not None
            assert latest_row[0] > 0  # Total AUM > 0
            assert latest_row[1] > 0  # Cost Basis > 0
    finally:
        conn.close()
