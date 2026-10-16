
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username="postgres",
    host="localhost",
    port=5432,
    database="industrial_sales_ops_analytics",
)


def main():
    print("Loading Customer and Ship-To Master Data")
    print("-" * 45)

    customers = pd.read_csv(
        DATA_DIR / "customers.csv",
        dtype={"customer_id": int},
    )

    # Convert CSV date strings into actual date values for PostgreSQL.
    customers["created_date"] = pd.to_datetime(
        customers["created_date"],
        format="%Y-%m-%d",
        errors="raise",
    ).dt.date

    ship_tos = pd.read_csv(
        DATA_DIR / "ship_tos.csv",
        dtype={"customer_id": int, "ship_to_id": int, "zip_code": str},
    )

    if len(customers) != 3000 or len(ship_tos) != 5000:
        raise ValueError("Unexpected customer or ship-to count.")

    if customers["customer_id"].duplicated().any():
        raise ValueError("Duplicate customer IDs.")

    if ship_tos["ship_to_id"].duplicated().any():
        raise ValueError("Duplicate ship-to IDs.")

    if not ship_tos["customer_id"].isin(customers["customer_id"]).all():
        raise ValueError("Ship-to references an unknown customer.")

    engine = create_engine(DATABASE_URL)

    with engine.begin() as connection:
        # Delete dependent ship-to records before parent customers.
        connection.execute(text("DELETE FROM core.ship_to"))
        connection.execute(text("DELETE FROM core.customer"))

        customers.to_sql(
            "customer",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
            chunksize=1000,
        )

        ship_tos.to_sql(
            "ship_to",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
            chunksize=1000,
        )

        customer_count = connection.execute(
            text("SELECT COUNT(*) FROM core.customer")
        ).scalar_one()

        ship_to_count = connection.execute(
            text("SELECT COUNT(*) FROM core.ship_to")
        ).scalar_one()

        if customer_count != len(customers):
            raise ValueError("Customer reconciliation failed.")

        if ship_to_count != len(ship_tos):
            raise ValueError("Ship-to reconciliation failed.")

    print(f"\nCustomers loaded: {customer_count:,}")
    print(f"Ship-to facilities loaded: {ship_to_count:,}")
    print("PASS: Customer and ship-to data loaded successfully.")


if __name__ == "__main__":
    main()
