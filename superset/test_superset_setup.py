"""
Verification tests for the Superset setup script.

Run inside the Superset container:
    docker exec -i portfolio_superset python < superset/test_superset_setup.py

Exit code 0 → all assertions passed.
Exit code 1 → at least one assertion failed (details printed to stdout).
"""

import sys
import logging

logging.basicConfig(level=logging.WARNING)

EXPECTED_CHARTS = [
    "Total AUM (EUR)",
    "Cost Basis (EUR)",
    "Total Return (EUR)",
    "Total Return (%)",
    "Portfolio Growth: AUM vs Cost Basis",
    "Quarterly PnL Performance",
    "Quarterly Dividend Cashflow",
    "Top Dividend Generating Stocks",
    "Top 10 Holdings by Market Value",
    "Top Gainers & Losers (Unrealised PnL)",
    "Currency & Regional Exposure",
    "Holdings Detail Table",
    "Portfolio Drawdown (Underwater Analysis)",
    "Dividend Yield on Cost per Ticker (%)",
    "Profit Attribution: Capital Gain vs Dividends",
]
EXPECTED_DASHBOARD = "Portfolio 360 Analytics"
EXPECTED_DATASETS  = [
    "daily_portfolio_metrics",
    "daily_holdings",
    "v_latest_holdings",
    "v_quarterly_portfolio_metrics",
    "v_quarterly_dividends",
    "v_top_dividend_tickers",
    "v_currency_exposure",
    "v_portfolio_drawdown",
    "v_dividend_yield_on_cost",
    "v_total_return_attribution",
]
EXPECTED_DB_NAME   = "Portfolio DWH"


def run_tests():
    from superset.app import create_app

    failures = []
    passed   = 0

    def check(label: str, condition: bool, detail: str = ""):
        nonlocal passed
        if condition:
            print(f"  [PASS] {label}")
            passed += 1
        else:
            msg = f"  [FAIL] {label}" + (f" — {detail}" if detail else "")
            print(msg)
            failures.append(label)

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.models.core import Database
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.slice import Slice
        from superset.models.dashboard import Dashboard

        print("\n── Database Connection ─────────────────────────────────────")
        database = db.session.query(Database).filter_by(database_name=EXPECTED_DB_NAME).first()
        check("Database connection exists", database is not None, f"'{EXPECTED_DB_NAME}' not found")
        if database:
            check(
                "SQLAlchemy URI correct",
                "postgres" in database.sqlalchemy_uri and "portfolio_dwh" in database.sqlalchemy_uri,
                database.sqlalchemy_uri,
            )

        print("\n── Datasets ────────────────────────────────────────────────")
        for table_name in EXPECTED_DATASETS:
            ds = (
                db.session.query(SqlaTable)
                .filter_by(table_name=table_name, schema="presentation")
                .first()
            )
            check(f"Dataset '{table_name}' exists", ds is not None)
            if ds:
                check(
                    f"Dataset '{table_name}' has columns",
                    len(ds.columns) > 0,
                    f"found {len(ds.columns)} columns",
                )

        print("\n── Charts ──────────────────────────────────────────────────")
        for chart_name in EXPECTED_CHARTS:
            slc = db.session.query(Slice).filter_by(slice_name=chart_name).first()
            check(f"Chart '{chart_name}' exists", slc is not None)

        check(
            f"All {len(EXPECTED_CHARTS)} charts present",
            len(failures) == 0 or all(c not in failures for c in EXPECTED_CHARTS),
        )

        print("\n── Dashboard ───────────────────────────────────────────────")
        dash = db.session.query(Dashboard).filter_by(dashboard_title=EXPECTED_DASHBOARD).first()
        check(f"Dashboard '{EXPECTED_DASHBOARD}' exists", dash is not None)

        if dash:
            import json

            check("Dashboard is published", dash.published is True)
            check(
                "Dashboard has position_json",
                bool(dash.position_json) and len(dash.position_json) > 10,
            )
            check(
                f"Dashboard contains all {len(EXPECTED_CHARTS)} slices",
                len(dash.slices) == len(EXPECTED_CHARTS),
                f"found {len(dash.slices)} slices",
            )

            # Native filters check
            meta = json.loads(dash.json_metadata or "{}")
            filters = meta.get("native_filter_configuration", [])
            check("Dashboard has json_metadata", bool(meta))
            check("Native filter configuration exists", len(filters) == 4, f"found {len(filters)} filters")
            
            filter_ids = [f.get("id") for f in filters]
            check("Native filter 'Time Range' present", "NATIVE_FILTER-time-range" in filter_ids)
            check("Native filter 'Asset Class' present", "NATIVE_FILTER-asset-class" in filter_ids)
            check("Native filter 'Currency & Region' present", "NATIVE_FILTER-currency" in filter_ids)
            check("Native filter 'Ticker Select' present", "NATIVE_FILTER-ticker" in filter_ids)

    print("\n" + "=" * 60)
    total = passed + len(failures)
    print(f"Results: {passed}/{total} tests passed, {len(failures)} failed.")
    if failures:
        print("Failed tests:")
        for f in failures:
            print(f"  • {f}")
        print("=" * 60)
        sys.exit(1)
    else:
        print("All tests passed. ✓")
        print("=" * 60)
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
