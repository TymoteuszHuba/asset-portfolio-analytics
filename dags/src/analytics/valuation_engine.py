"""
Valuation and Accounting Engine.
Calculates historical daily position balances, weighted average cost basis,
realized/unrealized PnL, FX currency conversions and overall portfolio market values.
Aligns with presentation.daily_portfolio_metrics and presentation.daily_holdings DWH schemas.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
import os
from typing import Dict, List, Any, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger("airflow.task")

DB_CONN_STRING = os.getenv(
    "DWH_CONN_STRING",
    "postgresql://portfolio_user:portfolio_password@postgres:5432/portfolio_dwh"
)


class ValuationEngine:
    """
    Core Accounting and Valuation Engine for Multi-Asset Portfolios.
    Base valuation currency is EUR.
    """

    def __init__(self, db_conn_string: Optional[str] = None):
        self.db_conn_string = db_conn_string or DB_CONN_STRING

    def _get_connection(self):
        return psycopg2.connect(self.db_conn_string)

    def calculate_portfolio_valuation(
        self
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Calculates daily valuation metrics and detailed asset holdings for the portfolio.
        Returns a tuple of (daily_portfolio_metrics, daily_holdings).
        """
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. Fetch chronological transactions
                cur.execute("""
                    SELECT transaction_date, ticker, type, quantity, 
                           unit_price_amount, unit_price_currency, 
                           operational_cost_amount, operational_cost_currency
                    FROM core.transaction_events
                    ORDER BY transaction_date ASC;
                """)
                transactions = cur.fetchall()

                if not transactions:
                    logger.warning("No transactions found in core.transaction_events.")
                    return [], []

                start_date = transactions[0]["transaction_date"]
                end_date = date.today()

                # 2. Fetch daily EOD asset prices (with LAP interpolation)
                cur.execute("""
                    SELECT price_date, ticker, close_price, currency
                    FROM core.asset_prices;
                """)
                asset_prices_rows = cur.fetchall()
                # Map (price_date, ticker) -> (close_price, currency)
                prices_map: Dict[Tuple[date, str], Tuple[Decimal, str]] = {
                    (r["price_date"], r["ticker"]): (Decimal(str(r["close_price"])), r["currency"])
                    for r in asset_prices_rows
                }

                # 3. Fetch FX rates from core.fx_rates (base_currency='EUR', quote_currency, rate_date, rate)
                cur.execute("""
                    SELECT rate_date, base_currency, quote_currency, rate
                    FROM core.fx_rates;
                """)
                fx_rows = cur.fetchall()
                # Map (rate_date, quote_currency) -> rate (EUR per 1 unit of quote_currency)
                fx_map: Dict[Tuple[date, str], Decimal] = {
                    (r["rate_date"], r["quote_currency"]): Decimal(str(r["rate"]))
                    for r in fx_rows
                }

            # Helper for FX conversion to EUR
            def get_fx_rate_to_eur(dt: date, curr: str) -> Decimal:
                curr = curr.upper()
                if curr == "EUR":
                    return Decimal("1.0")
                if (dt, curr) in fx_map and fx_map[(dt, curr)] > 0:
                    return fx_map[(dt, curr)]
                # Fallback to 1.0 if FX rate missing
                return Decimal("1.0")

            # Organize transactions by date
            txns_by_date: Dict[date, List[Dict[str, Any]]] = {}
            for t in transactions:
                t_date = t["transaction_date"]
                txns_by_date.setdefault(t_date, []).append(t)

            # Accounting state per ticker
            holdings_state: Dict[str, Dict[str, Any]] = {}

            daily_metrics_list: List[Dict[str, Any]] = []
            daily_holdings_list: List[Dict[str, Any]] = []

            curr_dt = start_date
            prev_aum_eur = Decimal("0.00")

            while curr_dt <= end_date:
                # Process transactions for today
                if curr_dt in txns_by_date:
                    for txn in txns_by_date[curr_dt]:
                        ticker = txn["ticker"]
                        t_type = str(txn["type"]).upper()
                        qty = Decimal(str(txn["quantity"]))
                        unit_price = Decimal(str(txn["unit_price_amount"]))
                        curr = str(txn["unit_price_currency"])
                        op_cost = Decimal(str(txn["operational_cost_amount"]))

                        fx_rate = get_fx_rate_to_eur(curr_dt, curr)
                        total_val_eur = (qty * unit_price * fx_rate) + (op_cost * fx_rate)

                        if ticker not in holdings_state:
                            holdings_state[ticker] = {
                                "quantity": Decimal("0"),
                                "cost_basis_eur": Decimal("0"),
                                "avg_cost_eur": Decimal("0"),
                                "realized_pl_eur": Decimal("0"),
                                "currency": curr
                            }

                        state = holdings_state[ticker]

                        if t_type == "BUY":
                            state["quantity"] += qty
                            state["cost_basis_eur"] += total_val_eur
                            if state["quantity"] > Decimal("0"):
                                state["avg_cost_eur"] = state["cost_basis_eur"] / state["quantity"]

                        elif t_type == "SELL":
                            if state["quantity"] > Decimal("0"):
                                cost_portion = state["avg_cost_eur"] * qty
                                proceeds_eur = (qty * unit_price * fx_rate) - (op_cost * fx_rate)
                                sale_pnl = proceeds_eur - cost_portion

                                state["realized_pl_eur"] += sale_pnl
                                state["quantity"] -= qty
                                state["cost_basis_eur"] -= cost_portion

                                if state["quantity"] <= Decimal("0"):
                                    state["quantity"] = Decimal("0")
                                    state["cost_basis_eur"] = Decimal("0")
                                    state["avg_cost_eur"] = Decimal("0")

                        elif t_type == "DIVIDEND":
                            div_net_eur = (qty * unit_price * fx_rate) - (op_cost * fx_rate)
                            state["realized_pl_eur"] += div_net_eur

                # Calculate valuation for active holdings on curr_dt
                day_total_aum_eur = Decimal("0.00")
                day_total_cost_basis_eur = Decimal("0.00")
                day_total_unrealized_pl_eur = Decimal("0.00")

                for ticker, state in holdings_state.items():
                    qty = state["quantity"]
                    if qty > Decimal("0"):
                        curr = state.get("currency", "USD")

                        # Look up asset price for curr_dt
                        if (curr_dt, ticker) in prices_map:
                            mkt_price, p_curr = prices_map[(curr_dt, ticker)]
                            mkt_fx = get_fx_rate_to_eur(curr_dt, p_curr)
                        else:
                            mkt_price = state["avg_cost_eur"]
                            mkt_fx = Decimal("1.0")

                        close_price_eur = mkt_price * mkt_fx
                        market_value_eur = qty * close_price_eur
                        unrealized_pl_eur = market_value_eur - state["cost_basis_eur"]

                        unrealized_pl_pct = (
                            (unrealized_pl_eur / state["cost_basis_eur"] * Decimal("100"))
                            if state["cost_basis_eur"] > Decimal("0")
                            else Decimal("0.00")
                        )

                        day_total_aum_eur += market_value_eur
                        day_total_cost_basis_eur += state["cost_basis_eur"]
                        day_total_unrealized_pl_eur += unrealized_pl_eur

                        daily_holdings_list.append({
                            "valuation_date": curr_dt,
                            "ticker": ticker,
                            "quantity": round(qty, 8),
                            "close_price_eur": round(close_price_eur, 4),
                            "market_value_eur": round(market_value_eur, 2),
                            "cost_basis_eur": round(state["cost_basis_eur"], 2),
                            "unrealized_pl_eur": round(unrealized_pl_eur, 2),
                            "unrealized_pl_pct": round(unrealized_pl_pct, 4),
                        })

                total_return_eur = day_total_aum_eur - day_total_cost_basis_eur
                total_return_pct = (
                    (total_return_eur / day_total_cost_basis_eur * Decimal("100"))
                    if day_total_cost_basis_eur > Decimal("0")
                    else Decimal("0.00")
                )

                daily_pl_eur = day_total_aum_eur - prev_aum_eur if prev_aum_eur > Decimal("0") else Decimal("0.00")
                prev_aum_eur = day_total_aum_eur

                daily_metrics_list.append({
                    "valuation_date": curr_dt,
                    "total_aum_eur": round(day_total_aum_eur, 2),
                    "cost_basis_eur": round(day_total_cost_basis_eur, 2),
                    "total_return_eur": round(total_return_eur, 2),
                    "total_return_pct": round(total_return_pct, 4),
                    "daily_pl_eur": round(daily_pl_eur, 2),
                })

                curr_dt += timedelta(days=1)

            return daily_metrics_list, daily_holdings_list

        finally:
            conn.close()


    def save_presentation_metrics(
        self,
        metrics: List[Dict[str, Any]],
        holdings: List[Dict[str, Any]]
    ) -> None:
        """
        Bulk upserts calculated valuation metrics into presentation.daily_portfolio_metrics
        and presentation.daily_holdings tables.
        """
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                if metrics:
                    m_query = """
                        INSERT INTO presentation.daily_portfolio_metrics (
                            valuation_date, total_aum_eur, cost_basis_eur,
                            total_return_eur, total_return_pct, daily_pl_eur
                        ) VALUES %s
                        ON CONFLICT (valuation_date)
                        DO UPDATE SET
                            total_aum_eur = EXCLUDED.total_aum_eur,
                            cost_basis_eur = EXCLUDED.cost_basis_eur,
                            total_return_eur = EXCLUDED.total_return_eur,
                            total_return_pct = EXCLUDED.total_return_pct,
                            daily_pl_eur = EXCLUDED.daily_pl_eur;
                    """
                    m_values = [
                        (
                            m["valuation_date"],
                            float(m["total_aum_eur"]),
                            float(m["cost_basis_eur"]),
                            float(m["total_return_eur"]),
                            float(m["total_return_pct"]),
                            float(m["daily_pl_eur"])
                        )
                        for m in metrics
                    ]
                    from psycopg2.extras import execute_values
                    execute_values(cur, m_query, m_values)

                if holdings:
                    h_query = """
                        INSERT INTO presentation.daily_holdings (
                            valuation_date, ticker, quantity, close_price_eur,
                            market_value_eur, cost_basis_eur, unrealized_pl_eur, unrealized_pl_pct
                        ) VALUES %s
                        ON CONFLICT (valuation_date, ticker)
                        DO UPDATE SET
                            quantity = EXCLUDED.quantity,
                            close_price_eur = EXCLUDED.close_price_eur,
                            market_value_eur = EXCLUDED.market_value_eur,
                            cost_basis_eur = EXCLUDED.cost_basis_eur,
                            unrealized_pl_eur = EXCLUDED.unrealized_pl_eur,
                            unrealized_pl_pct = EXCLUDED.unrealized_pl_pct;
                    """
                    h_values = [
                        (
                            h["valuation_date"],
                            h["ticker"],
                            float(h["quantity"]),
                            float(h["close_price_eur"]),
                            float(h["market_value_eur"]),
                            float(h["cost_basis_eur"]),
                            float(h["unrealized_pl_eur"]),
                            float(h["unrealized_pl_pct"])
                        )
                        for h in holdings
                    ]
                    execute_values(cur, h_query, h_values)

                conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()


def run_portfolio_valuation() -> Dict[str, Any]:
    """
    Executes portfolio valuation engine and saves results to presentation schema.
    """
    engine = ValuationEngine()
    metrics, holdings = engine.calculate_portfolio_valuation()
    
    if metrics:
        engine.save_presentation_metrics(metrics, holdings)

    logger.info(f"Valuation Engine calculated and saved {len(metrics)} daily metrics and {len(holdings)} holdings records to presentation schema.")
    
    return {
        "daily_metrics_count": len(metrics),
        "daily_holdings_count": len(holdings),
    }
