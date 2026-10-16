
import csv
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = (
    PROJECT_ROOT / "data" / "processed" / "erp_2025_final"
)

EXPECTED_FILES = 12
EXPECTED_SHIPMENTS = 453318
EXPECTED_RETURNS = 627
EXPECTED_TOTAL = 453945
EXPECTED_NET_SALES = Decimal("500092428.09")

DB_CONNECTION = (
    "host=localhost "
    "port=5432 "
    "dbname=industrial_sales_ops_analytics "
    "user=postgres"
)

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


def get_monthly_files():
    """Identify the twelve expected ERP extracts."""
    files = [
        INPUT_DIR / f"erp_posted_sales_2025_{month:02d}.csv"
        for month in range(1, 13)
    ]

    for path in files:
        if not path.is_file():
            raise FileNotFoundError(path)

    return files


def csv_records(path):
    """Read the source file with its original text values."""
    with path.open(
        "r", encoding="utf-8-sig", newline=""
    ) as handle:
        reader = csv.DictReader(handle)

        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError(
                f"Unexpected CSV columns: {path.name}"
            )

        for row_number, record in enumerate(reader, start=1):
            if None in record or None in record.values():
                raise ValueError(
                    f"Malformed CSV row in {path.name}: "
                    f"{row_number}"
                )

            yield row_number, record


def validate_source_files(files):
    """Check inputs before opening a database transaction."""
    print("Validating consolidated source files...")

    transaction_ids = set()
    shipment_ids = set()
    return_references = []

    shipments = 0
    returns = 0
    net_sales = Decimal("0.00")

    for month, path in enumerate(files, start=1):
        period = f"2025-{month:02d}"
        file_count = 0
        file_total = Decimal("0.00")

        for row_number, record in csv_records(path):
            transaction_id = record["transaction_id"]
            transaction_type = record["transaction_type"]

            if not transaction_id:
                raise ValueError("Blank transaction ID.")

            if transaction_id in transaction_ids:
                raise ValueError(
                    f"Duplicate transaction ID: {transaction_id}"
                )

            transaction_ids.add(transaction_id)

            posting = date.fromisoformat(
                record["posting_date"]
            )

            if (
                posting.year != 2025
                or posting.month != month
            ):
                raise ValueError(
                    f"Incorrect posting month: {transaction_id}"
                )

            if record["source_file_name"] != path.name:
                raise ValueError(
                    f"Source filename mismatch: {transaction_id}"
                )

            if int(record["source_row_number"]) != row_number:
                raise ValueError(
                    f"Source row mismatch: {transaction_id}"
                )

            quantity = Decimal(record["quantity"])
            unit_price = Decimal(
                record["unit_selling_price"]
            )
            amount = Decimal(
                record["posted_sales_amount"]
            )

            if record["currency_code"] != "USD":
                raise ValueError("Unexpected currency.")

            if transaction_type == "SHIPMENT":
                if (
                    quantity <= 0
                    or unit_price <= 0
                    or amount <= 0
                ):
                    raise ValueError(
                        f"Invalid shipment: {transaction_id}"
                    )

                shipment_ids.add(transaction_id)
                shipments += 1

            elif transaction_type == "RETURN":
                if (
                    quantity >= 0
                    or unit_price <= 0
                    or amount >= 0
                ):
                    raise ValueError(
                        f"Invalid return: {transaction_id}"
                    )

                return_references.append(
                    record["reference_transaction_id"]
                )
                returns += 1

            else:
                raise ValueError(
                    f"Unexpected transaction type: "
                    f"{transaction_type}"
                )

            file_total += amount
            file_count += 1

        net_sales += file_total

        print(
            f"{period}: {file_count:,} rows | "
            f"${file_total:,.2f} net"
        )

    for reference in return_references:
        if reference not in shipment_ids:
            raise ValueError(
                f"Unknown return reference: {reference}"
            )

    total = shipments + returns

    if shipments != EXPECTED_SHIPMENTS:
        raise ValueError("Shipment count mismatch.")

    if returns != EXPECTED_RETURNS:
        raise ValueError("Return count mismatch.")

    if total != EXPECTED_TOTAL:
        raise ValueError("Total record count mismatch.")

    if net_sales != EXPECTED_NET_SALES:
        raise ValueError("Annual net sales mismatch.")

    print("\nPASS: All source files reconciled.")

    return {
        "shipments": shipments,
        "returns": returns,
        "total": total,
        "net_sales": net_sales,
    }


def load_staging(files, expected):
    """Bulk-load staging in one PostgreSQL transaction."""
    column_sql = ", ".join(CSV_COLUMNS)

    copy_sql = (
        f"COPY staging.erp_sales_raw ({column_sql}) "
        "FROM STDIN"
    )

    # Uses the existing ~/.pgpass credentials.
    # Nothing is saved to a project configuration file.
    with psycopg.connect(DB_CONNECTION) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM staging.erp_sales_raw"
            )
            existing_count = cursor.fetchone()[0]

            if existing_count != 0:
                raise ValueError(
                    "Staging already contains "
                    f"{existing_count:,} records. "
                    "No data was loaded."
                )

            print("\nLoading PostgreSQL staging...")

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

            cursor.execute(
                """
                SELECT
                    COUNT(*) AS total_records,
                    COUNT(*) FILTER (
                        WHERE transaction_type = 'SHIPMENT'
                    ) AS shipment_records,
                    COUNT(*) FILTER (
                        WHERE transaction_type = 'RETURN'
                    ) AS return_records,
                    SUM(
                        posted_sales_amount::numeric
                    ) AS net_sales
                FROM staging.erp_sales_raw;
                """
            )

            (
                actual_total,
                actual_shipments,
                actual_returns,
                actual_net_sales,
            ) = cursor.fetchone()

            if actual_total != expected["total"]:
                raise ValueError("Staging record count mismatch.")

            if actual_shipments != expected["shipments"]:
                raise ValueError("Staging shipment count mismatch.")

            if actual_returns != expected["returns"]:
                raise ValueError("Staging return count mismatch.")

            if actual_net_sales != expected["net_sales"]:
                raise ValueError("Staging net sales mismatch.")

        # The connection commits only after all checks pass.

    print("\nPostgreSQL Staging Load Summary")
    print("-" * 45)
    print(f"Staged transactions: {actual_total:,}")
    print(f"Shipments: {actual_shipments:,}")
    print(f"Returns: {actual_returns:,}")
    print(f"Net posted sales: ${actual_net_sales:,.2f}")
    print("\nPASS: Staging load committed successfully.")


def main():
    print("2025 ERP Sales — PostgreSQL Staging Load")
    print("-" * 55)

    files = get_monthly_files()
    expected = validate_source_files(files)

    load_staging(files, expected)


if __name__ == "__main__":
    main()
