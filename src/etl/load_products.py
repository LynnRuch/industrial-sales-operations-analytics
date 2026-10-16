
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
    print("Loading Synthetic Product Catalog")
    print("-" * 45)

    categories = pd.read_csv(
        DATA_DIR / "product_categories.csv"
    )

    families = pd.read_csv(
        DATA_DIR / "product_families.csv"
    )

    products = pd.read_csv(
        DATA_DIR / "products.csv"
    )

    # Convert the CSV boolean field to actual Boolean values.
    products["active_flag"] = products["active_flag"].map(
        {True: True, False: False, "True": True, "False": False}
    )

    if (
        len(categories) != 4
        or len(families) != 24
        or len(products) != 1200
    ):
        raise ValueError("Product master record counts do not match.")

    if (
        categories["category_id"].duplicated().any()
        or families["family_id"].duplicated().any()
        or products["product_id"].duplicated().any()
        or products["sku"].duplicated().any()
    ):
        raise ValueError("Duplicate product master identifiers.")

    if products["active_flag"].isna().any():
        raise ValueError("Invalid product active_flag value.")

    engine = create_engine(DATABASE_URL)

    with engine.begin() as connection:
        # Clear child records before parent records.
        connection.execute(text("DELETE FROM core.product"))
        connection.execute(text("DELETE FROM core.product_family"))
        connection.execute(text("DELETE FROM core.product_category"))

        # Load parents before children to satisfy foreign keys.
        categories.to_sql(
            "product_category",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
        )

        families.to_sql(
            "product_family",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
        )

        products.to_sql(
            "product",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
            chunksize=1000,
        )

        counts = connection.execute(
            text("""
                SELECT
                    (SELECT COUNT(*) FROM core.product_category),
                    (SELECT COUNT(*) FROM core.product_family),
                    (SELECT COUNT(*) FROM core.product)
            """)
        ).one()

        if tuple(counts) != (4, 24, 1200):
            raise ValueError(
                f"Product reconciliation failed: {tuple(counts)}"
            )

    print(f"\nCategories loaded: {counts[0]:,}")
    print(f"Families loaded: {counts[1]:,}")
    print(f"SKUs loaded: {counts[2]:,}")
    print("PASS: Product catalog loaded and reconciled.")


if __name__ == "__main__":
    main()
