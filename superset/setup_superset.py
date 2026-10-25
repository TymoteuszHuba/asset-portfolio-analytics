"""
Automated Apache Superset Setup Script.
Connects Superset to the PostgreSQL Data Warehouse (presentation schema)
and registers analytical datasets: daily_portfolio_metrics and daily_holdings.
"""

import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("superset_setup")

DB_NAME = "Portfolio DWH"
SQLALCHEMY_URI = "postgresql://portfolio_user:portfolio_password@postgres:5432/portfolio_dwh"

DATASETS = [
    ("daily_portfolio_metrics", "presentation"),
    ("daily_holdings", "presentation"),
]


def setup_database_and_datasets():
    """
    Initializes PostgreSQL DWH database connection and registers presentation schema datasets.
    """
    from superset.app import create_app

    app = create_app()
    with app.app_context():
        from superset import db
        from superset.connectors.sqla.models import SqlaTable
        from superset.models.core import Database

        # 1. Register PostgreSQL Database Connection
        logger.info(f"Checking database connection: '{DB_NAME}'...")
        database = db.session.query(Database).filter_by(database_name=DB_NAME).first()

        if not database:
            logger.info(f"Creating database connection '{DB_NAME}' with URI: {SQLALCHEMY_URI}...")
            database = Database(database_name=DB_NAME, sqlalchemy_uri=SQLALCHEMY_URI)
            db.session.add(database)
            db.session.commit()
            logger.info(f"Database connection '{DB_NAME}' created successfully.")
        else:
            logger.info(f"Database connection '{DB_NAME}' already exists (ID: {database.id}).")

        # 2. Register Datasets
        for table_name, schema in DATASETS:
            logger.info(f"Checking dataset: {schema}.{table_name}...")
            existing_table = (
                db.session.query(SqlaTable)
                .filter_by(database_id=database.id, table_name=table_name, schema=schema)
                .first()
            )

            if not existing_table:
                logger.info(f"Registering dataset: {schema}.{table_name}...")
                table = SqlaTable(
                    table_name=table_name,
                    schema=schema,
                    database=database,
                )
                table.fetch_metadata()
                db.session.add(table)
                db.session.commit()
                logger.info(
                    f"Dataset '{schema}.{table_name}' registered successfully with {len(table.columns)} columns."
                )
            else:
                logger.info(
                    f"Dataset '{schema}.{table_name}' already exists with {len(existing_table.columns)} columns."
                )

    logger.info("Superset database and dataset setup completed successfully.")


if __name__ == "__main__":
    setup_database_and_datasets()
