
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "2025_returns.csv"
)

YEAR = 2025
RANDOM_SEED = 202509

ANNUAL_RETURN_TARGET = Decimal("500000.00")
TARGET_TOLERANCE = Decimal("0.03")
MAX_SINGLE_RETURN = Decimal("10000.00")


def round_money(value):
    """Round to cents using the project's rounding rule."""
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


def load_shipments():
    """Load the twelve validated monthly shipment exports."""
    frames = []

    for month in range(1, 13):
        path = RAW_DIR / f"erp_sales_2025_{month:02d}.csv"

        if not path.is_file():
            raise FileNotFoundError(path)

        frame = pd.read_csv(
            path,
            dtype={
                "transaction_id": str,
                "posting_date": str,
                "quantity": str,
                "unit_selling_price": str,
                "posted_sales_amount": str,
            },
        )

        if not frame["transaction_type"].eq("SHIPMENT").all():
            raise ValueError(
                f"Unexpected transaction type in {path.name}"
            )

        frames.append(frame)

    shipments = pd.concat(frames, ignore_index=True)

    if len(shipments) != 453318:
        raise ValueError(
            "Shipment count differs from our validated baseline."
        )

    if not shipments["transaction_id"].is_unique:
        raise ValueError("Duplicate shipment transaction IDs.")

    return shipments


def generate_returns(shipments):
    """Create rare returns referencing original shipments."""
    rng = np.random.default_rng(RANDOM_SEED)

    records = []
    total_returns = Decimal("0.00")
    latest_posting_date = date(2025, 12, 31)

    # Randomize eligible shipments without altering source files.
    candidate_indices = rng.permutation(len(shipments))

    for index in candidate_indices:
        if total_returns >= ANNUAL_RETURN_TARGET * Decimal(
            "0.99"
        ):
            break

        original = shipments.iloc[int(index)]

        original_date = date.fromisoformat(
            original.posting_date
        )

        # Returns post 2–45 days after the original shipment.
        days_later = int(rng.integers(2, 46))
        return_date = original_date + timedelta(
            days=days_later
        )

        if return_date > latest_posting_date:
            continue

        shipped_quantity = Decimal(original.quantity)
        unit_price = Decimal(original.unit_selling_price)

        if shipped_quantity <= 0 or unit_price <= 0:
            raise ValueError("Invalid original shipment.")

        maximum_quantity = int(shipped_quantity)

        if maximum_quantity < 1:
            continue

        # A return may involve only part of the shipped quantity.
        returned_units = int(
            rng.integers(1, maximum_quantity + 1)
        )

        returned_quantity = Decimal(returned_units)

        return_amount = round_money(
            returned_quantity * unit_price
        )

        if return_amount <= 0:
            continue

        # Avoid unusually large individual returns.
        if return_amount > MAX_SINGLE_RETURN:
            continue

        # This is a target, not a balancing transaction.
        if (
            total_returns + return_amount
            > ANNUAL_RETURN_TARGET * Decimal("1.01")
        ):
            continue

        sequence = len(records) + 1
        posting_month = return_date.strftime("%Y%m")

        records.append(
            {
                "transaction_id": (
                    f"RET-2025-{sequence:08d}"
                ),
                "transaction_type": "RETURN",
                "posting_date": return_date.isoformat(),
                "sales_order_number": original.sales_order_number,
                "sales_order_line": int(original.sales_order_line),
                "shipment_number": original.shipment_number,
                "shipment_line": int(original.shipment_line),
                "customer_id": int(original.customer_id),
                "ship_to_id": int(original.ship_to_id),
                "product_id": int(original.product_id),
                "quantity": f"{-returned_quantity:.3f}",
                "unit_selling_price": f"{unit_price:.4f}",
                "posted_sales_amount": f"{-return_amount:.2f}",
                "currency_code": "USD",
                "reference_transaction_id": original.transaction_id,
                "source_file_name": (
                    f"erp_returns_{posting_month}.csv"
                ),
                "source_row_number": 0,
                "load_batch_id": f"RET-{posting_month}",
            }
        )

        total_returns += return_amount

    return records, total_returns


def validate_returns(result, shipments, return_total):
    """Check references, signs, quantities, and posting dates."""
    if result.empty:
        raise ValueError("No returns generated.")

    if not result["transaction_id"].is_unique:
        raise ValueError("Duplicate return transaction IDs.")

    if result["reference_transaction_id"].duplicated().any():
        raise ValueError(
            "Multiple returns reference the same shipment."
        )

    shipment_lookup = shipments.set_index("transaction_id")

    if not result["reference_transaction_id"].isin(
        shipment_lookup.index
    ).all():
        raise ValueError("Unknown shipment reference.")

    validated_total = Decimal("0.00")

    for row in result.itertuples(index=False):
        original = shipment_lookup.loc[
            row.reference_transaction_id
        ]

        quantity = Decimal(row.quantity)
        amount = Decimal(row.posted_sales_amount)
        original_quantity = Decimal(original.quantity)
        original_price = Decimal(original.unit_selling_price)

        if quantity >= 0 or amount >= 0:
            raise ValueError("Invalid return transaction signs.")

        if abs(quantity) > original_quantity:
            raise ValueError(
                "Returned quantity exceeds shipped quantity."
            )

        expected_amount = round_money(
            quantity * original_price
        )

        if amount != expected_amount:
            raise ValueError(
                f"Return amount mismatch: {row.transaction_id}"
            )

        if (
            int(row.customer_id) != int(original.customer_id)
            or int(row.ship_to_id) != int(original.ship_to_id)
            or int(row.product_id) != int(original.product_id)
        ):
            raise ValueError(
                f"Shipment relationship mismatch: "
                f"{row.transaction_id}"
            )

        return_date = date.fromisoformat(row.posting_date)
        shipment_date = date.fromisoformat(
            original.posting_date
        )

        if not (
            shipment_date < return_date
            and return_date.year == YEAR
        ):
            raise ValueError("Invalid return posting date.")

        validated_total += abs(amount)

    if validated_total != return_total:
        raise ValueError("Return total failed reconciliation.")

    difference = abs(
        return_total - ANNUAL_RETURN_TARGET
    )

    if difference > (
        ANNUAL_RETURN_TARGET * TARGET_TOLERANCE
    ):
        raise ValueError(
            "Annual returns outside the expected 3% range."
        )


def main():
    print("Generating 2025 ERP Returns")
    print("-" * 50)

    shipments = load_shipments()

    records, return_total = generate_returns(shipments)

    result = pd.DataFrame(records)

    validate_returns(result, shipments, return_total)

    # Assign sequential source rows within each monthly return file.
    result = result.sort_values(
        ["posting_date", "transaction_id"]
    ).reset_index(drop=True)

    result["source_row_number"] = (
        result.groupby("source_file_name").cumcount() + 1
    )

    shipment_sales = sum(
        (
            Decimal(value)
            for value in shipments["posted_sales_amount"]
        ),
        Decimal("0.00"),
    )

    net_sales = shipment_sales - return_total

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(OUTPUT_PATH, index=False)

    print(f"\nOriginal shipment lines: {len(shipments):,}")
    print(f"Return transactions: {len(result):,}")
    print(f"Annual returned merchandise: ${return_total:,.2f}")

    print(f"\nShipment sales: ${shipment_sales:,.2f}")
    print(f"Net posted sales: ${net_sales:,.2f}")

    print(
        "Return rate: "
        f"{return_total / shipment_sales * 100:.4f}%"
    )

    print("\nPASS: Return transactions validated.")
    print(f"Saved to: {OUTPUT_PATH}")
    print("Original monthly shipment files remain unchanged.")


if __name__ == "__main__":
    main()
