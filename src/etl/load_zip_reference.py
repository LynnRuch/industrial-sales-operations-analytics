
from pathlib import Path
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "processed" / "us_zip_reference_2026.csv"

load_dotenv(PROJECT_ROOT / ".env")


def build_database_url():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    return URL.create(
        drivername="postgresql+psycopg",
        username=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "industrial_sales_ops_analytics"),
    )


def main():
    print("Loading ZIP Reference into PostgreSQL")
    print("-" * 45)

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Missing source file: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH, dtype={"zip_code": str})

    if len(df) != 33300:
        raise ValueError(
            f"Unexpected ZIP record count: {len(df):,}"
        )

    required_columns = [
        "zip_code", "city", "state_name", "state_code",
        "county", "latitude", "longitude",
    ]

    if df[required_columns].isna().any().any():
        raise ValueError("ZIP reference contains missing values.")

    database_url = build_database_url()
    engine = create_engine(database_url)

    with engine.begin() as connection:
        # Reload safely without accumulating duplicate records.
        connection.execute(text("DELETE FROM core.zip_reference"))

        df.to_sql(
            name="zip_reference",
            con=connection,
            schema="core",
            if_exists="append",
            index=False,
            chunksize=1000,
        )

        row_count = connection.execute(
            text("SELECT COUNT(*) FROM core.zip_reference")
        ).scalar_one()

        if row_count != len(df):
            raise ValueError(
                f"Reconciliation failure: CSV={len(df)}, "
                f"PostgreSQL={row_count}"
            )

    print(f"CSV records: {len(df):,}")
    print(f"PostgreSQL records: {row_count:,}")
    print("PASS: ZIP reference loaded and reconciled.")


if __name__ == "__main__":
    main()
