
from decimal import Decimal
from pathlib import Path

import pandas as pd
from sqlalchemy import Numeric, create_engine, text
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "processed" / "product_prices.csv"

DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username="postgres",
    host="localhost",
    port=5432,
    database="industrial_sales_ops_analytics",
)


def main():
    print("Loading Synthetic Product Selling Prices")
    print("-" * 45)

    # Read prices as text to preserve decimal precision.
    prices = pd.read_csv(
        CSV_PATH,
        dtype={
            "product_id": int,
            "base_unit_price": str,
            "currency_code": str,
        },
    )

    # Validate record counts and identifiers.
    if len(prices) != 1200:
        raise ValueError("Expected exactly 1,200 price records.")

    if prices["product_id"].duplicated().any():
        raise ValueError("Duplicate product IDs in price reference.")

    # Convert price strings to exact decimal values.
    prices["base_unit_price"] = prices["base_unit_price"].map(
        Decimal
    )

    if prices["base_unit_price"].le(Decimal("0")).any():
        raise ValueError("Base selling prices must be positive.")

    if not prices["currency_code"].eq("USD").all():
        raise ValueError("Unexpected currency code.")

    # Establish PostgreSQL connection using local .pgpass credentials.
    engine = create_engine(DATABASE_URL)

    # All database changes occur inside one transaction.
    # If anything fails, PostgreSQL rolls back the load.
    with engine.begin() as connection:

        # Verify the product master is populated.
        product_count = connection.execute(
            text("SELECT COUNT(*) FROM core.product")
        ).scalar_one()

        if product_count != 1200:
            raise ValueError(
                f"Expected 1,200 products; found {product_count:,}."
            )

        # Remove previous prices to make repeat loads safe.
        connection.execute(
            text("DELETE FROM core.product_price_reference")
        )

        # Load prices with an explicit PostgreSQL-compatible numeric type.
        prices.to_sql(
            name="product_price_reference",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
            chunksize=500,
            dtype={"base_unit_price": Numeric(18, 4)},
        )

        # Reconcile the loaded record count.
        loaded_count = connection.execute(
            text(
                "SELECT COUNT(*) "
                "FROM core.product_price_reference"
            )
        ).scalar_one()

        if loaded_count != len(prices):
            raise ValueError(
                f"Product price reconciliation failed: "
                f"CSV={len(prices):,}, "
                f"PostgreSQL={loaded_count:,}"
            )

    print(f"\nPrice records in CSV: {len(prices):,}")
    print(f"Price records in PostgreSQL: {loaded_count:,}")
    print("PASS: Product prices loaded and reconciled.")


if __name__ == "__main__":
    main()
