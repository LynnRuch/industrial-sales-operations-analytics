
"""
Export validated PostgreSQL analytics views to Parquet for Power BI.

Source: PostgreSQL on Fedora Linux
Destination: data/exports/powerbi/

Read-only database access.
Batch-based Parquet writing.
Exact decimal values preserved.
No existing exports are overwritten.
"""

import json
import shutil
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_DIR = PROJECT_ROOT / "data" / "exports" / "powerbi"

DB_CONNECTION = (
    "host=localhost "
    "port=5432 "
    "dbname=industrial_sales_ops_analytics "
    "user=postgres"
)

BATCH_SIZE = 25000

EXPORTS = {
    "fact_sales_transactions": (
        "analytics.fact_sales_transactions", 810340
    ),
    "dim_date": (
        "analytics.dim_date", 730
    ),
    "dim_customer": (
        "analytics.dim_customer", 3000
    ),
    "dim_ship_to": (
        "analytics.dim_ship_to", 5000
    ),
    "dim_product": (
        "analytics.dim_product", 1200
    ),
    "dim_sales_rep": (
        "analytics.dim_sales_rep", 84
    ),
}

EXPECTED_REVENUE = {
    2025: Decimal("500092428.09"),
    2026: Decimal("392981461.96"),
}

EXPECTED_ROWS = {
    2025: 453945,
    2026: 356395,
}


# ============================================================
# POSTGRESQL TO ARROW DATA TYPES
# ============================================================

def arrow_type(pg_oid):
    """Map PostgreSQL data types to explicit Parquet types."""

    mapping = {
        16: pa.bool_(),
        20: pa.int64(),
        21: pa.int16(),
        23: pa.int32(),
        25: pa.string(),
        1042: pa.string(),
        1043: pa.string(),
        1082: pa.date32(),
        700: pa.float32(),
        701: pa.float64(),
        1700: pa.decimal128(28, 4),
        1114: pa.timestamp("us"),
        1184: pa.timestamp("us", tz="UTC"),
    }

    if pg_oid not in mapping:
        raise ValueError(
            f"Unsupported PostgreSQL type OID: {pg_oid}"
        )

    return mapping[pg_oid]


# ============================================================
# VALIDATE POSTGRESQL SOURCE
# ============================================================

def validate_database(connection):
    print("Validating PostgreSQL analytics source...")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                calendar_year,
                COUNT(*),
                COALESCE(SUM(net_sales_amount), 0)
            FROM analytics.fact_sales_transactions
            GROUP BY calendar_year
            ORDER BY calendar_year
            """
        )

        results = cursor.fetchall()

    if len(results) != 2:
        raise ValueError(
            "Unexpected reporting years in fact data."
        )

    for year, count, revenue in results:
        if year not in EXPECTED_REVENUE:
            raise ValueError(
                f"Unexpected year: {year}"
            )

        if count != EXPECTED_ROWS[year]:
            raise ValueError(
                f"{year} transaction count mismatch."
            )

        if revenue != EXPECTED_REVENUE[year]:
            raise ValueError(
                f"{year} revenue mismatch."
            )

        print(
            f"{year}: {count:,} transactions | "
            f"${revenue:,.2f}"
        )

    print("PASS: Source revenue and counts reconcile.\n")

    return {
        str(year): {
            "transactions": count,
            "net_sales": str(revenue),
        }
        for year, count, revenue in results
    }


# ============================================================
# EXPORT ONE VIEW
# ============================================================

def export_view(
    connection,
    export_name,
    source_view,
    expected_rows,
    output_directory,
):
    output_path = (
        output_directory / f"{export_name}.parquet"
    )

    total_rows = 0
    exported_revenue = Decimal("0.00")

    with connection.cursor(
        name=f"powerbi_{export_name}"
    ) as cursor:

        cursor.execute(
            f"SELECT * FROM {source_view}"
        )

        column_names = [
            column.name
            for column in cursor.description
        ]

        schema = pa.schema([
            pa.field(
                column.name,
                arrow_type(column.type_code),
            )
            for column in cursor.description
        ])

        writer = None

        try:
            while True:
                rows = cursor.fetchmany(BATCH_SIZE)

                if not rows:
                    break

                columns = {
                    name: []
                    for name in column_names
                }

                for row in rows:
                    for index, name in enumerate(
                        column_names
                    ):
                        columns[name].append(
                            row[index]
                        )

                if export_name == "fact_sales_transactions":
                    exported_revenue += sum(
                        (
                            value
                            for value in columns[
                                "net_sales_amount"
                            ]
                            if value is not None
                        ),
                        Decimal("0.00"),
                    )

                arrays = [
                    pa.array(
                        columns[field.name],
                        type=field.type,
                    )
                    for field in schema
                ]

                table = pa.Table.from_arrays(
                    arrays,
                    schema=schema,
                )

                if writer is None:
                    writer = pq.ParquetWriter(
                        output_path,
                        schema,
                        compression="snappy",
                    )

                writer.write_table(table)
                total_rows += len(rows)

        finally:
            if writer is not None:
                writer.close()

    if total_rows != expected_rows:
        raise ValueError(
            f"{export_name}: expected "
            f"{expected_rows:,} rows, "
            f"exported {total_rows:,}."
        )

    if export_name == "fact_sales_transactions":
        expected_total = sum(
            EXPECTED_REVENUE.values(),
            Decimal("0.00"),
        )

        if exported_revenue != expected_total:
            raise ValueError(
                "Fact export revenue failed reconciliation."
            )

    metadata = pq.read_metadata(output_path)

    if metadata.num_rows != expected_rows:
        raise ValueError(
            f"{export_name}: Parquet row count mismatch."
        )

    print(
        f"PASS: {export_name}.parquet "
        f"| {total_rows:,} rows"
    )

    return {
        "file": output_path.name,
        "source": source_view,
        "rows": total_rows,
        "columns": column_names,
        "bytes": output_path.stat().st_size,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("Industrial Sales Operations Analytics")
    print("Power BI Parquet Export")
    print("=" * 65)

    # Never overwrite existing exports.
    if EXPORT_DIR.exists():
        raise FileExistsError(
            "Export directory already exists. "
            "Existing exports are protected:\n"
            f"{EXPORT_DIR}"
        )

    EXPORT_DIR.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix=".powerbi_build_",
            dir=EXPORT_DIR.parent,
        )
    )

    try:
        with psycopg.connect(
            DB_CONNECTION
        ) as connection:

            # All queries use one consistent read-only
            # snapshot of the PostgreSQL database.
            connection.execute(
                "SET TRANSACTION ISOLATION LEVEL "
                "REPEATABLE READ, READ ONLY"
            )

            yearly_totals = validate_database(
                connection
            )

            exported_files = []

            for name, (
                source_view,
                expected_rows,
            ) in EXPORTS.items():

                result = export_view(
                    connection,
                    name,
                    source_view,
                    expected_rows,
                    temporary_directory,
                )

                exported_files.append(result)

        manifest = {
            "project": (
                "Industrial Sales Operations Analytics"
            ),
            "exported_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "reporting_through": "2026-09-30",
            "transaction_rows": 810340,
            "total_net_sales": "893073890.05",
            "yearly_totals": yearly_totals,
            "files": exported_files,
        }

        manifest_path = (
            temporary_directory / "export_manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
            ),
            encoding="utf-8",
        )

        # Publish only after every export validates.
        if EXPORT_DIR.exists():
            raise FileExistsError(
                f"Export destination exists: {EXPORT_DIR}"
            )

        temporary_directory.rename(
            EXPORT_DIR
        )

    except Exception:
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
        raise

    print("\n" + "=" * 65)
    print("PASS: All Power BI exports completed.")
    print(f"Files: {len(EXPORTS)} Parquet datasets")
    print("Transactions: 810,340")
    print("Net sales: $893,073,890.05")
    print(f"Saved to: {EXPORT_DIR}")


if __name__ == "__main__":
    main()
