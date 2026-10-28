"""
Automated Apache Superset Setup Script.

Connects Superset to the PostgreSQL Data Warehouse (presentation schema),
registers analytical datasets, creates/updates high-readability investment charts
and assembles them into an advanced 3-tab 'Portfolio 360 Analytics' executive dashboard:
  - Tab 1: Executive Overview
  - Tab 2: Holdings & Allocation (dynamic filtering with Asset Class, Currency, Ticker)
  - Tab 3: Advanced Risk & Performance (Drawdown, Yield on Cost, Profit Attribution)

Run inside the Superset container:
    docker exec -i portfolio_superset python < superset/setup_superset.py
"""

import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("superset_setup")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DB_NAME = "Portfolio DWH"
SQLALCHEMY_URI = "postgresql://portfolio_user:portfolio_password@postgres:5432/portfolio_dwh"

DATASETS = [
    ("daily_portfolio_metrics", "presentation"),
    ("daily_holdings", "presentation"),
    ("v_latest_holdings", "presentation"),
    ("v_quarterly_portfolio_metrics", "presentation"),
    ("v_quarterly_dividends", "presentation"),
    ("v_top_dividend_tickers", "presentation"),
    ("v_currency_exposure", "presentation"),
    ("v_portfolio_drawdown", "presentation"),
    ("v_dividend_yield_on_cost", "presentation"),
    ("v_total_return_attribution", "presentation"),
]

DASHBOARD_TITLE = "Portfolio 360 Analytics"

QUARTERLY_METRICS_DS = "v_quarterly_portfolio_metrics"
DIVIDENDS_DS         = "v_quarterly_dividends"
TOP_DIVIDENDS_DS     = "v_top_dividend_tickers"
LATEST_HOLDINGS_DS   = "v_latest_holdings"
DRAWDOWN_DS          = "v_portfolio_drawdown"
YIELD_ON_COST_DS     = "v_dividend_yield_on_cost"
PROFIT_ATTR_DS       = "v_total_return_attribution"


def _make_charts_spec():
    """Return an updated list of chart specifications for all 3 dashboard tabs."""
    return [
        # ── Tab 1: Executive Overview ────────────────────────────────────────
        (
            "Total AUM (EUR)",
            "big_number_total",
            QUARTERLY_METRICS_DS,
            {
                "viz_type": "big_number_total",
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "total_aum_eur"},
                    "aggregate": "MAX",
                    "label": "Total AUM (EUR)",
                },
                "subheader": "Latest Portfolio Market Value (EUR)",
                "y_axis_format": ",.2f",
                "time_range": "No filter",
            },
        ),
        (
            "Cost Basis (EUR)",
            "big_number_total",
            QUARTERLY_METRICS_DS,
            {
                "viz_type": "big_number_total",
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "cost_basis_eur"},
                    "aggregate": "MAX",
                    "label": "Invested Capital (EUR)",
                },
                "subheader": "Total Capital Deposited / Invested",
                "y_axis_format": ",.2f",
                "time_range": "No filter",
            },
        ),
        (
            "Total Return (EUR)",
            "big_number_total",
            QUARTERLY_METRICS_DS,
            {
                "viz_type": "big_number_total",
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "total_return_eur"},
                    "aggregate": "MAX",
                    "label": "Total Return (EUR)",
                },
                "subheader": "Realised + Unrealised Profit (EUR)",
                "y_axis_format": ",.2f",
                "time_range": "No filter",
            },
        ),
        (
            "Total Return (%)",
            "big_number_total",
            QUARTERLY_METRICS_DS,
            {
                "viz_type": "big_number_total",
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "total_return_pct"},
                    "aggregate": "MAX",
                    "label": "Total Return (%)",
                },
                "subheader": "Return on Invested Capital",
                "y_axis_format": ",.2f",
                "time_range": "No filter",
            },
        ),
        (
            "Portfolio Growth: AUM vs Cost Basis",
            "echarts_timeseries_line",
            QUARTERLY_METRICS_DS,
            {
                "viz_type": "echarts_timeseries_line",
                "x_axis": "quarter_start",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "total_aum_eur"},
                        "aggregate": "MAX",
                        "label": "Market Value (AUM EUR)",
                    },
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "cost_basis_eur"},
                        "aggregate": "MAX",
                        "label": "Invested Cost (EUR)",
                    },
                ],
                "time_range": "No filter",
                "y_axis_format": ",.0f",
                "y_axis_title": "Valuation in EUR",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "show_legend": True,
                "zoomable": True,
                "markerSize": 6,
                "area": True,
                "opacity": 0.15,
            },
        ),
        (
            "Quarterly PnL Performance",
            "echarts_timeseries_bar",
            QUARTERLY_METRICS_DS,
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "quarter_start",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "quarterly_pl_eur"},
                        "aggregate": "SUM",
                        "label": "Quarterly PnL (EUR)",
                    }
                ],
                "time_range": "No filter",
                "y_axis_format": ",.0f",
                "y_axis_title": "Profit / Loss (EUR)",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "show_legend": False,
                "zoomable": True,
                "color_scheme": "bnbColors",
            },
        ),
        (
            "Quarterly Dividend Cashflow",
            "echarts_timeseries_bar",
            DIVIDENDS_DS,
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "quarter_start",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "dividend_amount_eur"},
                        "aggregate": "SUM",
                        "label": "Dividends Received (EUR)",
                    }
                ],
                "time_range": "No filter",
                "y_axis_format": ",.0f",
                "y_axis_title": "Dividends in EUR",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "show_legend": False,
                "zoomable": True,
                "color_scheme": "supersetColors",
            },
        ),
        (
            "Top Dividend Generating Stocks",
            "echarts_timeseries_bar",
            TOP_DIVIDENDS_DS,
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "ticker",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "total_dividends_eur"},
                        "aggregate": "SUM",
                        "label": "Total Dividends Received (EUR)",
                    }
                ],
                "time_range": "No filter",
                "show_legend": False,
                "y_axis_format": ",.2f",
                "y_axis_title": "EUR",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "order_desc": True,
                "row_limit": 10,
            },
        ),
        # ── Tab 2: Holdings & Allocation ────────────────────────────────────
        (
            "Top 10 Holdings by Market Value",
            "echarts_timeseries_bar",
            LATEST_HOLDINGS_DS,
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "ticker",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "market_value_eur"},
                        "aggregate": "SUM",
                        "label": "Market Value (EUR)",
                    }
                ],
                "time_range": "No filter",
                "show_legend": False,
                "y_axis_format": ",.2f",
                "y_axis_title": "EUR",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "order_desc": True,
                "row_limit": 10,
            },
        ),
        (
            "Top Gainers & Losers (Unrealised PnL)",
            "echarts_timeseries_bar",
            LATEST_HOLDINGS_DS,
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "ticker",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "unrealized_pl_eur"},
                        "aggregate": "SUM",
                        "label": "Unrealised Gain / Loss (EUR)",
                    }
                ],
                "time_range": "No filter",
                "show_legend": False,
                "y_axis_format": ",.2f",
                "y_axis_title": "EUR",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "order_desc": True,
                "row_limit": 15,
            },
        ),
        (
            "Currency & Regional Exposure",
            "pie",
            LATEST_HOLDINGS_DS,
            {
                "viz_type": "pie",
                "groupby": ["currency_region"],
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "market_value_eur"},
                    "aggregate": "SUM",
                    "label": "Market Value (EUR)",
                },
                "donut": True,
                "innerRadius": 40,
                "show_labels": True,
                "show_legend": True,
                "number_format": ",.2f",
            },
        ),
        (
            "Holdings Detail Table",
            "table",
            LATEST_HOLDINGS_DS,
            {
                "viz_type": "table",
                "groupby": [],
                "all_columns": [
                    "ticker",
                    "asset_class",
                    "currency_region",
                    "quantity",
                    "close_price_eur",
                    "market_value_eur",
                    "cost_basis_eur",
                    "unrealized_pl_eur",
                    "unrealized_pl_pct",
                ],
                "time_range": "No filter",
                "order_by_cols": ["[\"market_value_eur\", false]"],
                "row_limit": 100,
                "include_time": False,
            },
        ),
        # ── Tab 3: Advanced Risk & Performance ──────────────────────────────
        (
            "Portfolio Drawdown (Underwater Analysis)",
            "echarts_timeseries_line",
            DRAWDOWN_DS,
            {
                "viz_type": "echarts_timeseries_line",
                "x_axis": "valuation_date",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "drawdown_pct"},
                        "aggregate": "MIN",
                        "label": "Drawdown from Peak (%)",
                    }
                ],
                "time_range": "No filter",
                "y_axis_format": ",.2f",
                "y_axis_title": "Drawdown %",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "show_legend": False,
                "zoomable": True,
                "area": True,
                "opacity": 0.25,
                "color_scheme": "d3Category20c",
            },
        ),
        (
            "Dividend Yield on Cost per Ticker (%)",
            "echarts_timeseries_bar",
            YIELD_ON_COST_DS,
            {
                "viz_type": "echarts_timeseries_bar",
                "x_axis": "ticker",
                "metrics": [
                    {
                        "expressionType": "SIMPLE",
                        "column": {"column_name": "yield_on_cost_pct"},
                        "aggregate": "MAX",
                        "label": "Yield on Cost (%)",
                    }
                ],
                "time_range": "No filter",
                "show_legend": False,
                "y_axis_format": ",.2f",
                "y_axis_title": "Annual YoC %",
                "y_axis_title_margin": 65,
                "left_margin": 80,
                "rich_tooltip": True,
                "order_desc": True,
                "row_limit": 15,
            },
        ),
        (
            "Profit Attribution: Capital Gain vs Dividends",
            "pie",
            PROFIT_ATTR_DS,
            {
                "viz_type": "pie",
                "groupby": ["profit_component"],
                "metric": {
                    "expressionType": "SIMPLE",
                    "column": {"column_name": "amount_eur"},
                    "aggregate": "SUM",
                    "label": "Profit Amount (EUR)",
                },
                "donut": True,
                "innerRadius": 40,
                "show_labels": True,
                "show_legend": True,
                "number_format": ",.2f",
                "color_scheme": "supersetColors",
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Dashboard layout (3 Tabs)
# ---------------------------------------------------------------------------

def _build_dashboard_layout(chart_ids: dict) -> dict:
    """
    Build Superset dashboard position JSON with 3 tabs and generous dimensions.
    """
    # Chart node IDs
    c_aum        = "CHART-aum"
    c_cost       = "CHART-cost"
    c_ret_eur    = "CHART-ret-eur"
    c_ret_pct    = "CHART-ret-pct"
    c_growth     = "CHART-growth"
    c_pnl        = "CHART-pnl"
    c_div        = "CHART-div"
    c_top_div    = "CHART-top-div"
    c_top_val    = "CHART-top-val"
    c_gainloss   = "CHART-gainloss"
    c_curr       = "CHART-curr"
    c_table      = "CHART-table"
    c_drawdown   = "CHART-drawdown"
    c_yoc        = "CHART-yoc"
    c_profit_att = "CHART-profit-att"

    # Row node IDs
    r_kpis     = "ROW-kpis"
    r_growth   = "ROW-growth"
    r_pnl_div  = "ROW-pnl-div"
    r_top_div  = "ROW-top-div"
    r_alloc_gl = "ROW-alloc-gl"
    r_table    = "ROW-table"
    r_dd       = "ROW-dd"
    r_risk2    = "ROW-risk2"

    # Tab node IDs
    tab1 = "TAB-overview"
    tab2 = "TAB-holdings"
    tab3 = "TAB-risk"
    tabs = "TABS-root"

    layout = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {
            "type": "ROOT",
            "id": "ROOT_ID",
            "children": [tabs],
            "parents": [],
        },
    }

    layout[tabs] = {
        "type": "TABS",
        "id": tabs,
        "children": [tab1, tab2, tab3],
        "parents": ["ROOT_ID"],
    }

    # ── Tab 1: Executive Overview ────────────────────────────────────────────
    layout[tab1] = {
        "type": "TAB",
        "id": tab1,
        "children": [r_kpis, r_growth, r_pnl_div, r_top_div],
        "meta": {"text": "Executive Overview", "defaultText": "Executive Overview"},
        "parents": [tabs],
    }

    # Row 1: 4 KPI Cards (width 3 each, height 18)
    layout[r_kpis] = {
        "type": "ROW",
        "id": r_kpis,
        "children": [c_aum, c_cost, c_ret_eur, c_ret_pct],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab1],
    }
    layout[c_aum]     = {"type": "CHART", "id": c_aum,     "children": [], "meta": {"chartId": chart_ids["Total AUM (EUR)"],                  "width": 3, "height": 18}, "parents": [r_kpis]}
    layout[c_cost]    = {"type": "CHART", "id": c_cost,    "children": [], "meta": {"chartId": chart_ids["Cost Basis (EUR)"],                 "width": 3, "height": 18}, "parents": [r_kpis]}
    layout[c_ret_eur] = {"type": "CHART", "id": c_ret_eur, "children": [], "meta": {"chartId": chart_ids["Total Return (EUR)"],                "width": 3, "height": 18}, "parents": [r_kpis]}
    layout[c_ret_pct] = {"type": "CHART", "id": c_ret_pct, "children": [], "meta": {"chartId": chart_ids["Total Return (%)"],                  "width": 3, "height": 18}, "parents": [r_kpis]}

    # Row 2: Portfolio Growth (AUM vs Cost Basis Area Chart) - full width 12, height 38
    layout[r_growth] = {
        "type": "ROW",
        "id": r_growth,
        "children": [c_growth],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab1],
    }
    layout[c_growth] = {"type": "CHART", "id": c_growth, "children": [], "meta": {"chartId": chart_ids["Portfolio Growth: AUM vs Cost Basis"], "width": 12, "height": 38}, "parents": [r_growth]}

    # Row 3: Quarterly PnL (width 6) + Quarterly Dividends (width 6), height 38
    layout[r_pnl_div] = {
        "type": "ROW",
        "id": r_pnl_div,
        "children": [c_pnl, c_div],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab1],
    }
    layout[c_pnl] = {"type": "CHART", "id": c_pnl, "children": [], "meta": {"chartId": chart_ids["Quarterly PnL Performance"],    "width": 6, "height": 38}, "parents": [r_pnl_div]}
    layout[c_div] = {"type": "CHART", "id": c_div, "children": [], "meta": {"chartId": chart_ids["Quarterly Dividend Cashflow"],   "width": 6, "height": 38}, "parents": [r_pnl_div]}

    # Row 4: Top Dividend Payers (width 12, height 36)
    layout[r_top_div] = {
        "type": "ROW",
        "id": r_top_div,
        "children": [c_top_div],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab1],
    }
    layout[c_top_div] = {"type": "CHART", "id": c_top_div, "children": [], "meta": {"chartId": chart_ids["Top Dividend Generating Stocks"], "width": 12, "height": 36}, "parents": [r_top_div]}

    # ── Tab 2: Holdings & Allocation ─────────────────────────────────────────
    layout[tab2] = {
        "type": "TAB",
        "id": tab2,
        "children": [r_alloc_gl, r_table],
        "meta": {"text": "Holdings & Allocation", "defaultText": "Holdings & Allocation"},
        "parents": [tabs],
    }

    # Row 1: Top 10 Holdings (width 5) + Top Gainers/Losers (width 4) + Currency (width 3), height 40
    layout[r_alloc_gl] = {
        "type": "ROW",
        "id": r_alloc_gl,
        "children": [c_top_val, c_gainloss, c_curr],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab2],
    }
    layout[c_top_val]  = {"type": "CHART", "id": c_top_val,  "children": [], "meta": {"chartId": chart_ids["Top 10 Holdings by Market Value"],          "width": 5, "height": 40}, "parents": [r_alloc_gl]}
    layout[c_gainloss] = {"type": "CHART", "id": c_gainloss, "children": [], "meta": {"chartId": chart_ids["Top Gainers & Losers (Unrealised PnL)"], "width": 4, "height": 40}, "parents": [r_alloc_gl]}
    layout[c_curr]     = {"type": "CHART", "id": c_curr,     "children": [], "meta": {"chartId": chart_ids["Currency & Regional Exposure"],             "width": 3, "height": 40}, "parents": [r_alloc_gl]}

    # Row 2: Holdings Detail Table (width 12, height 44)
    layout[r_table] = {
        "type": "ROW",
        "id": r_table,
        "children": [c_table],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab2],
    }
    layout[c_table] = {"type": "CHART", "id": c_table, "children": [], "meta": {"chartId": chart_ids["Holdings Detail Table"], "width": 12, "height": 44}, "parents": [r_table]}

    # ── Tab 3: Advanced Risk & Performance ───────────────────────────────────
    layout[tab3] = {
        "type": "TAB",
        "id": tab3,
        "children": [r_dd, r_risk2],
        "meta": {"text": "Advanced Risk & Performance", "defaultText": "Advanced Risk & Performance"},
        "parents": [tabs],
    }

    # Row 1: Portfolio Drawdown (full width 12, height 38)
    layout[r_dd] = {
        "type": "ROW",
        "id": r_dd,
        "children": [c_drawdown],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab3],
    }
    layout[c_drawdown] = {"type": "CHART", "id": c_drawdown, "children": [], "meta": {"chartId": chart_ids["Portfolio Drawdown (Underwater Analysis)"], "width": 12, "height": 38}, "parents": [r_dd]}

    # Row 2: Yield on Cost (width 8) + Profit Attribution (width 4), height 40
    layout[r_risk2] = {
        "type": "ROW",
        "id": r_risk2,
        "children": [c_yoc, c_profit_att],
        "meta": {"background": "BACKGROUND_TRANSPARENT"},
        "parents": [tab3],
    }
    layout[c_yoc]        = {"type": "CHART", "id": c_yoc,        "children": [], "meta": {"chartId": chart_ids["Dividend Yield on Cost per Ticker (%)"],        "width": 8, "height": 40}, "parents": [r_risk2]}
    layout[c_profit_att] = {"type": "CHART", "id": c_profit_att, "children": [], "meta": {"chartId": chart_ids["Profit Attribution: Capital Gain vs Dividends"], "width": 4, "height": 40}, "parents": [r_risk2]}

    return layout


# ---------------------------------------------------------------------------
# Setup & update functions
# ---------------------------------------------------------------------------

def setup_database_and_datasets():
    """Initializes database and datasets. Returns (database, datasource_map)."""
    from superset import db
    from superset.connectors.sqla.models import SqlaTable
    from superset.models.core import Database

    logger.info(f"Checking database connection: '{DB_NAME}'...")
    database = db.session.query(Database).filter_by(database_name=DB_NAME).first()

    if not database:
        logger.info(f"Creating database connection '{DB_NAME}'...")
        database = Database(database_name=DB_NAME, sqlalchemy_uri=SQLALCHEMY_URI)
        db.session.add(database)
        db.session.commit()
        logger.info(f"Database connection '{DB_NAME}' created (ID: {database.id}).")
    else:
        logger.info(f"Database connection '{DB_NAME}' already exists (ID: {database.id}).")

    datasource_map = {}
    for table_name, schema in DATASETS:
        logger.info(f"Checking dataset: {schema}.{table_name}...")
        existing = (
            db.session.query(SqlaTable)
            .filter_by(database_id=database.id, table_name=table_name, schema=schema)
            .first()
        )
        if not existing:
            logger.info(f"Registering dataset: {schema}.{table_name}...")
            tbl = SqlaTable(table_name=table_name, schema=schema, database=database)
            tbl.fetch_metadata()
            db.session.add(tbl)
            db.session.commit()
            logger.info(f"Dataset '{schema}.{table_name}' registered ({len(tbl.columns)} columns).")
            datasource_map[table_name] = tbl
        else:
            existing.fetch_metadata()
            db.session.commit()
            logger.info(
                f"Dataset '{schema}.{table_name}' refreshed ({len(existing.columns)} columns)."
            )
            datasource_map[table_name] = existing

    return database, datasource_map


def upsert_charts(datasource_map):
    """
    Creates or updates the analytical charts with generous margins and layout.
    Returns: {slice_name -> Slice.id}
    """
    from superset import db
    from superset.models.slice import Slice

    chart_ids = {}
    charts_spec = _make_charts_spec()

    for slice_name, viz_type, datasource_table, params in charts_spec:
        logger.info(f"Upserting chart: '{slice_name}'...")
        datasource = datasource_map.get(datasource_table)
        if not datasource:
            logger.warning(f"Datasource '{datasource_table}' not found – skipping '{slice_name}'.")
            continue

        existing = db.session.query(Slice).filter_by(slice_name=slice_name).first()

        if existing:
            existing.viz_type = viz_type
            existing.datasource_id = datasource.id
            existing.datasource_type = "table"
            existing.params = json.dumps(params)
            db.session.commit()
            logger.info(f"Chart '{slice_name}' updated (ID: {existing.id}).")
            chart_ids[slice_name] = existing.id
        else:
            slc = Slice(
                slice_name=slice_name,
                viz_type=viz_type,
                datasource_id=datasource.id,
                datasource_type="table",
                params=json.dumps(params),
            )
            db.session.add(slc)
            db.session.commit()
            logger.info(f"Chart '{slice_name}' created (ID: {slc.id}).")
            chart_ids[slice_name] = slc.id

    return chart_ids


def _build_native_filters(datasource_map: dict) -> list:
    """
    Constructs Native Dashboard Filters configuration for Superset:
    1. Time Range Filter (scoped to time-series datasets)
    2. Asset Class Filter (Stocks vs REITs vs ETFs)
    3. Currency & Region Filter (USD vs EUR)
    4. Ticker Filter (multi-select on latest holdings)
    """
    quarterly_ds = datasource_map.get(QUARTERLY_METRICS_DS)
    latest_ds = datasource_map.get(LATEST_HOLDINGS_DS)

    filters = [
        {
            "id": "NATIVE_FILTER-time-range",
            "name": "Time Range",
            "filterType": "filter_time",
            "targets": [
                {
                    "datasetId": quarterly_ds.id if quarterly_ds else None,
                    "column": {"name": "quarter_start"},
                }
            ],
            "defaultDataMask": {
                "extraFormData": {
                    "time_range": "No filter"
                },
                "filterState": {
                    "value": "No filter"
                }
            },
            "controlObject": {
                "enableEmptyFilter": True,
            },
            "cascadeParentIds": [],
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": []
            },
            "isInstant": True,
        },
        {
            "id": "NATIVE_FILTER-asset-class",
            "name": "Asset Class",
            "filterType": "filter_select",
            "targets": [
                {
                    "datasetId": latest_ds.id if latest_ds else None,
                    "column": {"name": "asset_class"},
                }
            ],
            "defaultDataMask": {
                "extraFormData": {},
                "filterState": {}
            },
            "controlObject": {
                "multiSelect": True,
                "enableEmptyFilter": True,
                "inverseSelection": False,
                "defaultToFirstItem": False,
            },
            "cascadeParentIds": [],
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": []
            },
            "isInstant": True,
        },
        {
            "id": "NATIVE_FILTER-currency",
            "name": "Currency & Region",
            "filterType": "filter_select",
            "targets": [
                {
                    "datasetId": latest_ds.id if latest_ds else None,
                    "column": {"name": "currency_region"},
                }
            ],
            "defaultDataMask": {
                "extraFormData": {},
                "filterState": {}
            },
            "controlObject": {
                "multiSelect": True,
                "enableEmptyFilter": True,
                "inverseSelection": False,
                "defaultToFirstItem": False,
            },
            "cascadeParentIds": [],
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": []
            },
            "isInstant": True,
        },
        {
            "id": "NATIVE_FILTER-ticker",
            "name": "Select Ticker(s)",
            "filterType": "filter_select",
            "targets": [
                {
                    "datasetId": latest_ds.id if latest_ds else None,
                    "column": {"name": "ticker"},
                }
            ],
            "defaultDataMask": {
                "extraFormData": {},
                "filterState": {}
            },
            "controlObject": {
                "multiSelect": True,
                "enableEmptyFilter": True,
                "inverseSelection": False,
                "defaultToFirstItem": False,
            },
            "cascadeParentIds": [],
            "scope": {
                "rootPath": ["ROOT_ID"],
                "excluded": []
            },
            "isInstant": True,
        }
    ]
    return filters


def upsert_dashboard(chart_ids: dict, datasource_map: dict):
    """
    Creates or updates the 'Portfolio 360 Analytics' dashboard with new layout, slices,
    and native filters across 3 tabs.
    """
    from superset import db
    from superset.models.dashboard import Dashboard
    from superset.models.slice import Slice

    logger.info(f"Upserting dashboard: '{DASHBOARD_TITLE}'...")
    position_json = _build_dashboard_layout(chart_ids)
    slices = (
        db.session.query(Slice)
        .filter(Slice.id.in_(chart_ids.values()))
        .all()
    )

    native_filters = _build_native_filters(datasource_map)
    json_metadata = {
        "native_filter_configuration": native_filters,
        "color_scheme": "supersetColors",
        "refresh_frequency": 0,
        "expanded_slices": {},
        "label_colors": {},
        "timed_refresh_immune_slices": [],
    }

    existing = db.session.query(Dashboard).filter_by(dashboard_title=DASHBOARD_TITLE).first()
    if existing:
        existing.position_json = json.dumps(position_json)
        existing.json_metadata = json.dumps(json_metadata)
        existing.slices = slices
        existing.published = True
        db.session.commit()
        logger.info(f"Dashboard '{DASHBOARD_TITLE}' updated across 3 tabs with Native Filters (ID: {existing.id}).")
        return existing
    else:
        dashboard = Dashboard(
            dashboard_title=DASHBOARD_TITLE,
            position_json=json.dumps(position_json),
            json_metadata=json.dumps(json_metadata),
            slices=slices,
            published=True,
        )
        db.session.add(dashboard)
        db.session.commit()
        logger.info(f"Dashboard '{DASHBOARD_TITLE}' created across 3 tabs with Native Filters (ID: {dashboard.id}).")
        return dashboard


def main():
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        _database, datasource_map = setup_database_and_datasets()
        chart_ids = upsert_charts(datasource_map)
        logger.info(f"Charts configured: {len(chart_ids)}  {list(chart_ids.keys())}")
        dashboard = upsert_dashboard(chart_ids, datasource_map)

        logger.info("=" * 60)
        logger.info("Superset configuration successfully updated!")
        logger.info(f"  Dashboard : '{DASHBOARD_TITLE}' (ID: {dashboard.id})")
        logger.info(f"  URL       : http://localhost:8088/superset/dashboard/{dashboard.id}/")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
