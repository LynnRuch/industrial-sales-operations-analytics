
"""
Append January–September 2026 ERP transactions to PostgreSQL staging.

Preserves all existing 2025 staging and core records.
Validates source files before any database changes.
Uses ROUND_HALF_UP for financial reconciliation.
Prevents duplicate 2026 staging loads.
Rolls back the entire transaction if database validation fails.
"""

import csv
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import psycopg


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "erp_2026_final"
)

DB_CONNECTION = (
    "host=localhost "
    "port=5432 "
    "dbname=industrial_sales_ops_analytics "
    "user=postgres"
)

EXPECTED_2025_COUNT = 453_945
EXPECTED_2025_NET = Decimal("500092428.09")

EXPECTED_SHIPMENTS = 355_949
EXPECTED_RETURNS = 446
EXPECTED_TOTAL = 356_395
EXPECTED_NET = Decimal("392981461.96")

MONEY_PRECISION = Decimal("0.01")

CSV_COLUMNS = [
    "transaction_id",
    "transaction_type",
    "posting_date",
    "sales_order_number",
    "sales_order_line",
    "shipment_number",
    "shipment_line",
    "customer_id",
    "ship_to_id",
    "product_id",
    "quantity",
    "unit_selling_price",
    "posted_sales_amount",
    "currency_code",
    "reference_transaction_id",
    "source_file_name",
    "source_row_number",
    "load_batch_id",
]


# ============================================================
# FINANCIAL CALCULATIONS
# ============================================================

def round_money(value):
    """Use the same rounding convention as the ERP generators."""
    return Decimal(str(value)).quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# SOURCE FILE DISCOVERY
# ============================================================

def get_source_files():
    """Locate all nine consolidated 2026 ERP extracts."""

    files = [
        INPUT_DIR / f"erp_posted_sales_2026_{month:02d}.csv"
        for month in range(1, 10)
    ]

    for path in files:
        if not path.is_file():
            raise FileNotFoundError(
                f"Missing ERP source file: {path}"
            )

    return files


# ============================================================
# CSV READING
# ============================================================

def csv_records(path):
    """Read CSV records while preserving original text values."""

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:

        reader = csv.DictReader(handle)

        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(
                f"Unexpected CSV structure: {path.name}"
            )

        for row_number, record in enumerate(
            reader,
            start=1,
        ):

            if (
                None in record
                or None in record.values()
            ):
                raise ValueError(
                    f"Malformed CSV row: "
                    f"{path.name}, row {row_number}"
                )

            yield row_number, record


# ============================================================
# VALIDATE ALL 2026 SOURCE FILES
# ============================================================

def validate_source_files(files):
    """
    Validate all transactions before connecting to PostgreSQL.
    No database records are modified here.
    """

    print("Validating 2026 consolidated ERP files...")
    print("-" * 65)

    transaction_ids = set()
    shipment_ids = set()
    return_references = []

    shipment_count = 0
    return_count = 0

    total_net_sales = Decimal("0.00")

    for month, path in enumerate(files, start=1):

        expected_period = f"2026-{month:02d}"

        monthly_count = 0
        monthly_net_sales = Decimal("0.00")

        for row_number, record in csv_records(path):

            transaction_id = record["transaction_id"]
            transaction_type = record["transaction_type"]

            # ----------------------------------------
            # Transaction identity
            # ----------------------------------------

            if not transaction_id:
                raise ValueError(
                    f"Blank transaction ID: {path.name}"
                )

            if transaction_id in transaction_ids:
                raise ValueError(
                    f"Duplicate transaction ID: {transaction_id}"
                )

            transaction_ids.add(transaction_id)

            # ----------------------------------------
            # Posting date and source metadata
            # ----------------------------------------

            posting_date = date.fromisoformat(
                record["posting_date"]
            )

            if (
                posting_date.year != 2026
                or posting_date.month != month
            ):
                raise ValueError(
                    f"Incorrect posting month: {transaction_id}"
                )

            if record["source_file_name"] != path.name:
                raise ValueError(
                    f"Source filename mismatch: {transaction_id}"
                )

            if int(
                record["source_row_number"]
            ) != row_number:
                raise ValueError(
                    f"Source row mismatch: {transaction_id}"
                )

            if record["currency_code"] != "USD":
                raise ValueError(
                    f"Unexpected currency: {transaction_id}"
                )

            # ----------------------------------------
            # Financial validation
            # ----------------------------------------

            quantity = Decimal(
                record["quantity"]
            )

            unit_price = Decimal(
                record["unit_selling_price"]
            )

            posted_amount = Decimal(
                record["posted_sales_amount"]
            )

            calculated_amount = round_money(
                quantity * unit_price
            )

            if posted_amount != calculated_amount:
                raise ValueError(
                    f"Financial mismatch: {transaction_id}"
                )

            if unit_price <= 0:
                raise ValueError(
                    f"Invalid unit price: {transaction_id}"
                )

            # ----------------------------------------
            # Transaction type rules
            # ----------------------------------------

            if transaction_type == "SHIPMENT":

                if (
                    quantity <= 0
                    or posted_amount <= 0
                ):
                    raise ValueError(
                        f"Invalid shipment: {transaction_id}"
                    )

                if record["reference_transaction_id"]:
                    raise ValueError(
                        f"Unexpected shipment reference: "
                        f"{transaction_id}"
                    )

                shipment_ids.add(transaction_id)
                shipment_count += 1

            elif transaction_type == "RETURN":

                if (
                    quantity >= 0
                    or posted_amount >= 0
                ):
                    raise ValueError(
                        f"Invalid return: {transaction_id}"
                    )

                if not record["reference_transaction_id"]:
                    raise ValueError(
                        f"Missing return reference: "
                        f"{transaction_id}"
                    )

                return_references.append(
                    record["reference_transaction_id"]
                )

                return_count += 1

            else:
                raise ValueError(
                    f"Unknown transaction type: "
                    f"{transaction_id}"
                )

            monthly_count += 1
            monthly_net_sales += posted_amount

        total_net_sales += monthly_net_sales

        print(
            f"{expected_period}: "
            f"{monthly_count:,} rows | "
            f"${monthly_net_sales:,.2f} net"
        )

    # --------------------------------------------
    # Return references
    # --------------------------------------------

    for reference in return_references:

        if reference not in shipment_ids:
            raise ValueError(
                f"Return references unknown shipment: "
                f"{reference}"
            )

    if len(return_references) != len(
        set(return_references)
    ):
        raise ValueError(
            "Multiple returns reference the same shipment."
        )

    # --------------------------------------------
    # Final 2026 source reconciliation
    # --------------------------------------------

    if shipment_count != EXPECTED_SHIPMENTS:
        raise ValueError(
            "2026 shipment count mismatch."
        )

    if return_count != EXPECTED_RETURNS:
        raise ValueError(
            "2026 return count mismatch."
        )

    if len(transaction_ids) != EXPECTED_TOTAL:
        raise ValueError(
            "2026 transaction count mismatch."
        )

    if total_net_sales != EXPECTED_NET:
        raise ValueError(
            "2026 net sales mismatch."
        )

    print("\n2026 Source Validation Summary")
    print("-" * 45)

    print(f"Shipments: {shipment_count:,}")
    print(f"Returns: {return_count:,}")
    print(f"Total transactions: {len(transaction_ids):,}")
    print(f"Net posted sales: ${total_net_sales:,.2f}")

    print("\nPASS: All 2026 source files reconciled.")

    return {
        "shipments": shipment_count,
        "returns": return_count,
        "total": len(transaction_ids),
        "net_sales": total_net_sales,
    }


# ============================================================
# POSTGRESQL YEAR TOTALS
# ============================================================

def get_year_totals(cursor, year):
    """Return the staging count and signed sales for one year."""

    cursor.execute(
        """
        SELECT
            COUNT(*),
            COALESCE(
                SUM(posted_sales_amount::numeric),
                0
            )
        FROM staging.erp_sales_raw
        WHERE LEFT(posting_date, 4) = %s
        """,
        (str(year),),
    )

    return cursor.fetchone()


# ============================================================
# APPEND 2026 TO POSTGRESQL STAGING
# ============================================================

def load_staging(files, expected):
    """
    Append 2026 transactions in one database transaction.

    Existing 2025 records are neither deleted nor updated.
    All inserts roll back if any validation fails.
    """

    print("\nChecking PostgreSQL staging...")
    print("-" * 65)

    copy_sql = (
        "COPY staging.erp_sales_raw ("
        + ", ".join(CSV_COLUMNS)
        + ") FROM STDIN"
    )

    with psycopg.connect(DB_CONNECTION) as connection:

        with connection.cursor() as cursor:

            # Coordinate concurrent runs of this loader.
            cursor.execute(
                "SELECT pg_advisory_xact_lock(2026, 1)"
            )

            # ----------------------------------------
            # Verify existing 2025 staging
            # ----------------------------------------

            existing_2025 = get_year_totals(
                cursor,
                2025,
            )

            if existing_2025 != (
                EXPECTED_2025_COUNT,
                EXPECTED_2025_NET,
            ):
                raise ValueError(
                    "2025 staging baseline does not match "
                    "the validated historical data. "
                    "No records were loaded."
                )

            # ----------------------------------------
            # Prevent duplicate 2026 imports
            # ----------------------------------------

            existing_2026 = get_year_totals(
                cursor,
                2026,
            )

            if existing_2026[0] != 0:
                raise ValueError(
                    "2026 transactions already exist "
                    "in staging. No records were loaded."
                )

            # ----------------------------------------
            # Confirm 2026 core has not been loaded
            # ----------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM core.sales_transaction
                WHERE posting_date >= DATE '2026-01-01'
                  AND posting_date < DATE '2027-01-01'
                """
            )

            existing_core_2026 = cursor.fetchone()[0]

            if existing_core_2026 != 0:
                raise ValueError(
                    "2026 transactions already exist in core. "
                    "No records were loaded."
                )

            print("2025 staging baseline: confirmed")
            print("Existing 2026 staging records: 0")
            print("Existing 2026 core records: 0")

            # ----------------------------------------
            # Append nine months using PostgreSQL COPY
            # ----------------------------------------

            print("\nAppending 2026 transactions...")

            with cursor.copy(copy_sql) as copy:

                for path in files:

                    for _, record in csv_records(path):

                        copy.write_row(
                            tuple(
                                record[column]
                                for column in CSV_COLUMNS
                            )
                        )

                    print(f"Loaded: {path.name}")

            # ----------------------------------------
            # Reconcile staging after insertion
            # ----------------------------------------

            actual_2025 = get_year_totals(
                cursor,
                2025,
            )

            actual_2026 = get_year_totals(
                cursor,
                2026,
            )

            if actual_2025 != existing_2025:
                raise ValueError(
                    "2025 staging baseline changed. "
                    "Transaction will be rolled back."
                )

            if actual_2026 != (
                expected["total"],
                expected["net_sales"],
            ):
                raise ValueError(
                    "2026 staging totals do not reconcile. "
                    "Transaction will be rolled back."
                )

            cursor.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE transaction_type = 'SHIPMENT'
                    ),
                    COUNT(*) FILTER (
                        WHERE transaction_type = 'RETURN'
                    )
                FROM staging.erp_sales_raw
                WHERE LEFT(posting_date, 4) = '2026'
                """
            )

            actual_shipments, actual_returns = (
                cursor.fetchone()
            )

            if actual_shipments != expected["shipments"]:
                raise ValueError(
                    "2026 staging shipment count mismatch. "
                    "Transaction will be rolled back."
                )

            if actual_returns != expected["returns"]:
                raise ValueError(
                    "2026 staging return count mismatch. "
                    "Transaction will be rolled back."
                )

        # Connection commits only after all validations pass.
        # Any exception inside the connection rolls back.

    # ========================================================
    # SUCCESS SUMMARY
    # ========================================================

    print("\nPostgreSQL Staging Load Summary")
    print("-" * 55)

    print(
        f"2025 staging preserved: "
        f"{existing_2025[0]:,} transactions"
    )

    print(
        f"2026 staging appended: "
        f"{actual_2026[0]:,} transactions"
    )

    print(
        f"Combined staging transactions: "
        f"{existing_2025[0] + actual_2026[0]:,}"
    )

    print(
        f"2026 net posted sales: "
        f"${actual_2026[1]:,.2f}"
    )

    print(
        "\nPASS: 2026 staging append "
        "committed successfully."
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("2026 ERP Sales — PostgreSQL Staging Append")
    print("=" * 65)

    files = get_source_files()

    expected = validate_source_files(files)

    load_staging(files, expected)


if __name__ == "__main__":
    main()
