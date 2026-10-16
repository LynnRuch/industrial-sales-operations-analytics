
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROCESSED_DIR / "erp_2025_final"

RETURN_FILE = PROCESSED_DIR / "2025_returns.csv"

EXPECTED_SHIPMENTS = 453318
EXPECTED_RETURNS = 627
EXPECTED_NET_SALES = Decimal("500092428.09")

CURRENCY_COLUMNS = [
    "quantity",
    "unit_selling_price",
    "posted_sales_amount",
]

TEXT_COLUMNS = [
    "transaction_id",
    "posting_date",
    "reference_transaction_id",
    "source_file_name",
    "load_batch_id",
]


def read_transactions(path):
    """Read transaction values without losing decimal precision."""
    return pd.read_csv(
        path,
        dtype={
            column: str
            for column in CURRENCY_COLUMNS + TEXT_COLUMNS
        },
        keep_default_na=False,
    )


def amount_total(frame):
    """Sum signed sales amounts using exact decimal arithmetic."""
    return sum(
        (Decimal(value) for value in frame["posted_sales_amount"]),
        Decimal("0.00"),
    )


def validate_originals(shipments, returns):
    """Validate counts, identifiers, and return relationships."""
    if len(shipments) != EXPECTED_SHIPMENTS:
        raise ValueError("Unexpected shipment count.")

    if len(returns) != EXPECTED_RETURNS:
        raise ValueError("Unexpected return count.")

    if not shipments["transaction_type"].eq("SHIPMENT").all():
        raise ValueError("Unexpected shipment transaction type.")

    if not returns["transaction_type"].eq("RETURN").all():
        raise ValueError("Unexpected return transaction type.")

    combined_ids = pd.concat(
        [shipments["transaction_id"], returns["transaction_id"]],
        ignore_index=True,
    )

    if not combined_ids.is_unique:
        raise ValueError("Duplicate transaction IDs.")

    if not returns["reference_transaction_id"].isin(
        shipments["transaction_id"]
    ).all():
        raise ValueError("Return references unknown shipment.")

    if returns["reference_transaction_id"].duplicated().any():
        raise ValueError("Duplicate original shipment references.")

    shipment_lookup = shipments.set_index("transaction_id")

    for row in returns.itertuples(index=False):
        original = shipment_lookup.loc[
            row.reference_transaction_id
        ]

        for field in (
            "customer_id",
            "ship_to_id",
            "product_id",
            "sales_order_number",
            "sales_order_line",
            "shipment_number",
            "shipment_line",
        ):
            if str(getattr(row, field)) != str(original[field]):
                raise ValueError(
                    f"Return relationship mismatch: {row.transaction_id}"
                )

        if row.posting_date <= original["posting_date"]:
            raise ValueError(
                f"Return posted before shipment: {row.transaction_id}"
            )

        quantity = Decimal(row.quantity)
        original_quantity = Decimal(original["quantity"])
        price = Decimal(original["unit_selling_price"])
        amount = Decimal(row.posted_sales_amount)

        expected_amount = (quantity * price).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        if (
            quantity >= 0
            or abs(quantity) > original_quantity
            or amount >= 0
            or amount != expected_amount
        ):
            raise ValueError(
                f"Invalid return values: {row.transaction_id}"
            )


def validate_month(frame, month):
    """Validate consolidated monthly transaction structure."""
    period = f"2025-{month:02d}"

    if frame.empty:
        raise ValueError(f"No transactions in {period}.")

    if not frame["transaction_id"].is_unique:
        raise ValueError(f"Duplicate IDs in {period}.")

    if not frame["posting_date"].str.startswith(period).all():
        raise ValueError(f"Incorrect posting month: {period}.")

    if not frame["transaction_type"].isin(
        ["SHIPMENT", "RETURN"]
    ).all():
        raise ValueError(f"Unexpected transaction type: {period}.")

    if not frame["currency_code"].eq("USD").all():
        raise ValueError(f"Unexpected currency: {period}.")

    if frame["transaction_id"].eq("").any():
        raise ValueError(f"Missing transaction ID: {period}.")

    for row in frame.itertuples(index=False):
        quantity = Decimal(row.quantity)
        price = Decimal(row.unit_selling_price)
        amount = Decimal(row.posted_sales_amount)

        expected = (quantity * price).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        if amount != expected:
            raise ValueError(
                f"Amount mismatch: {row.transaction_id}"
            )

        if row.transaction_type == "SHIPMENT":
            if quantity <= 0 or price <= 0 or amount <= 0:
                raise ValueError(
                    f"Invalid shipment: {row.transaction_id}"
                )

        elif row.transaction_type == "RETURN":
            if quantity >= 0 or price <= 0 or amount >= 0:
                raise ValueError(
                    f"Invalid return: {row.transaction_id}"
                )


def main():
    print("Consolidating 2025 ERP Transactions")
    print("-" * 65)

    shipment_frames = []

    for month in range(1, 13):
        path = RAW_DIR / f"erp_sales_2025_{month:02d}.csv"

        if not path.is_file():
            raise FileNotFoundError(path)

        shipment_frames.append(read_transactions(path))

    shipments = pd.concat(
        shipment_frames,
        ignore_index=True,
    )

    if not RETURN_FILE.is_file():
        raise FileNotFoundError(RETURN_FILE)

    returns = read_transactions(RETURN_FILE)

    validate_originals(shipments, returns)

    all_transactions = pd.concat(
        [shipments, returns],
        ignore_index=True,
    )

    if all_transactions["posting_date"].str[:4].ne("2025").any():
        raise ValueError("Transactions outside 2025.")

    # Do not silently overwrite previously generated final files.
    if OUTPUT_DIR.exists() and any(OUTPUT_DIR.iterdir()):
        raise FileExistsError(
            f"Output folder is not empty: {OUTPUT_DIR}"
        )

    # Validate all twelve files before writing any of them.
    monthly_outputs = []
    validated_total = Decimal("0.00")
    validated_count = 0

    for month in range(1, 13):
        period = f"2025-{month:02d}"
        filename = f"erp_posted_sales_2025_{month:02d}.csv"

        frame = all_transactions.loc[
            all_transactions["posting_date"].str.startswith(period)
        ].copy()

        frame = frame.sort_values(
            ["posting_date", "transaction_id"]
        ).reset_index(drop=True)

        # These fields describe the final consolidated extract.
        frame["source_file_name"] = filename
        frame["source_row_number"] = range(
            1, len(frame) + 1
        )

        validate_month(frame, month)

        monthly_total = amount_total(frame)
        validated_total += monthly_total
        validated_count += len(frame)

        shipment_count = int(
            frame["transaction_type"].eq("SHIPMENT").sum()
        )
        return_count = int(
            frame["transaction_type"].eq("RETURN").sum()
        )

        monthly_outputs.append((filename, frame))

        print(
            f"{period} | "
            f"{shipment_count:>7,} shipments | "
            f"{return_count:>4,} returns | "
            f"${monthly_total:>14,.2f} net"
        )

    if validated_count != (
        EXPECTED_SHIPMENTS + EXPECTED_RETURNS
    ):
        raise ValueError("Annual transaction count mismatch.")

    if validated_total != EXPECTED_NET_SALES:
        raise ValueError(
            "Annual net sales do not reconcile."
        )

    if validated_total != amount_total(all_transactions):
        raise ValueError("Consolidation changed sales totals.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for filename, frame in monthly_outputs:
        frame.to_csv(
            OUTPUT_DIR / filename,
            index=False,
        )

    print("\nFull-Year Consolidation Summary")
    print("-" * 45)
    print(f"Monthly ERP files: {len(monthly_outputs)}")
    print(f"Shipment records: {len(shipments):,}")
    print(f"Return records: {len(returns):,}")
    print(f"Total transaction records: {validated_count:,}")
    print(f"Net posted sales: ${validated_total:,.2f}")

    print("\nPASS: All 12 consolidated ERP files validated.")
    print(f"Saved to: {OUTPUT_DIR}")
    print("Original shipment and return files remain unchanged.")


if __name__ == "__main__":
    main()
