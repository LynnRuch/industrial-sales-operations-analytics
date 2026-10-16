
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_DIR = PROJECT_ROOT / "data" / "raw"

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "2026_returns.csv"
)

YEAR = 2026
MONTHS = range(1, 10)
RANDOM_SEED = 202609

EXPECTED_SHIPMENT_LINES = 355949

# Nine-month equivalent of the 2025 annual return target.
RETURN_TARGET = Decimal("375000.00")
TARGET_TOLERANCE = Decimal("0.03")
MAX_SINGLE_RETURN = Decimal("10000.00")

LAST_POSTING_DATE = date(2026, 9, 30)


# ============================================================
# MONEY HANDLING
# ============================================================

def round_money(value):
    return Decimal(str(value)).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )


# ============================================================
# LOAD 2026 SHIPMENTS
# ============================================================

def load_shipments():
    frames = []

    for month in MONTHS:
        path = (
            RAW_DIR
            / f"erp_sales_{YEAR}_{month:02d}.csv"
        )

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

        if not frame["transaction_type"].eq(
            "SHIPMENT"
        ).all():
            raise ValueError(
                f"Unexpected transaction type: {path.name}"
            )

        if not frame["posting_date"].str.startswith(
            f"{YEAR}-{month:02d}"
        ).all():
            raise ValueError(
                f"Incorrect posting month: {path.name}"
            )

        frames.append(frame)

    shipments = pd.concat(
        frames,
        ignore_index=True,
    )

    if len(shipments) != EXPECTED_SHIPMENT_LINES:
        raise ValueError(
            "2026 shipment count differs "
            "from the validated baseline."
        )

    if not shipments["transaction_id"].is_unique:
        raise ValueError(
            "Duplicate shipment transaction IDs."
        )

    if shipments["posted_sales_amount"].isna().any():
        raise ValueError(
            "Missing shipment revenue."
        )

    return shipments


# ============================================================
# GENERATE RETURN TRANSACTIONS
# ============================================================

def generate_returns(shipments):
    rng = np.random.default_rng(RANDOM_SEED)

    records = []
    total_returns = Decimal("0.00")

    candidate_indices = rng.permutation(
        len(shipments)
    )

    for index in candidate_indices:

        if total_returns >= (
            RETURN_TARGET * Decimal("0.99")
        ):
            break

        original = shipments.iloc[int(index)]

        shipment_date = date.fromisoformat(
            original.posting_date
        )

        days_later = int(
            rng.integers(2, 46)
        )

        return_date = (
            shipment_date
            + timedelta(days=days_later)
        )

        # Returns beyond September are outside
        # the completed 2026 reporting period.
        if return_date > LAST_POSTING_DATE:
            continue

        shipped_quantity = Decimal(
            original.quantity
        )

        unit_price = Decimal(
            original.unit_selling_price
        )

        if (
            shipped_quantity <= 0
            or unit_price <= 0
        ):
            raise ValueError(
                "Invalid original shipment."
            )

        maximum_quantity = int(
            shipped_quantity
        )

        if maximum_quantity < 1:
            continue

        returned_units = int(
            rng.integers(
                1,
                maximum_quantity + 1,
            )
        )

        returned_quantity = Decimal(
            returned_units
        )

        return_amount = round_money(
            returned_quantity * unit_price
        )

        if return_amount <= 0:
            continue

        if return_amount > MAX_SINGLE_RETURN:
            continue

        if (
            total_returns + return_amount
            > RETURN_TARGET * Decimal("1.01")
        ):
            continue

        sequence = len(records) + 1

        posting_month = return_date.strftime(
            "%Y%m"
        )

        records.append({
            "transaction_id": (
                f"RET-{YEAR}-{sequence:08d}"
            ),
            "transaction_type": "RETURN",
            "posting_date": return_date.isoformat(),
            "sales_order_number": (
                original.sales_order_number
            ),
            "sales_order_line": int(
                original.sales_order_line
            ),
            "shipment_number": (
                original.shipment_number
            ),
            "shipment_line": int(
                original.shipment_line
            ),
            "customer_id": int(
                original.customer_id
            ),
            "ship_to_id": int(
                original.ship_to_id
            ),
            "product_id": int(
                original.product_id
            ),
            "quantity": (
                f"{-returned_quantity:.3f}"
            ),
            "unit_selling_price": (
                f"{unit_price:.4f}"
            ),
            "posted_sales_amount": (
                f"{-return_amount:.2f}"
            ),
            "currency_code": "USD",
            "reference_transaction_id": (
                original.transaction_id
            ),
            "source_file_name": (
                f"erp_returns_{posting_month}.csv"
            ),
            "source_row_number": 0,
            "load_batch_id": (
                f"RET-{posting_month}"
            ),
        })

        total_returns += return_amount

    return records, total_returns


# ============================================================
# VALIDATION
# ============================================================

def validate_returns(
    returns,
    shipments,
    return_total,
):

    if returns.empty:
        raise ValueError(
            "No returns were generated."
        )

    if not returns["transaction_id"].is_unique:
        raise ValueError(
            "Duplicate return transaction IDs."
        )

    if returns[
        "reference_transaction_id"
    ].duplicated().any():
        raise ValueError(
            "Multiple returns reference one shipment."
        )

    originals = shipments.set_index(
        "transaction_id"
    )

    if not returns[
        "reference_transaction_id"
    ].isin(originals.index).all():
        raise ValueError(
            "Return references an unknown shipment."
        )

    validated_total = Decimal("0.00")

    for row in returns.itertuples(index=False):

        original = originals.loc[
            row.reference_transaction_id
        ]

        quantity = Decimal(
            row.quantity
        )

        amount = Decimal(
            row.posted_sales_amount
        )

        original_quantity = Decimal(
            original.quantity
        )

        original_price = Decimal(
            original.unit_selling_price
        )

        if quantity >= 0 or amount >= 0:
            raise ValueError(
                "Return must have negative "
                "quantity and revenue."
            )

        if abs(quantity) > original_quantity:
            raise ValueError(
                "Return quantity exceeds shipment."
            )

        expected_amount = round_money(
            quantity * original_price
        )

        if amount != expected_amount:
            raise ValueError(
                f"Amount mismatch: {row.transaction_id}"
            )

        if (
            int(row.customer_id)
            != int(original.customer_id)
            or int(row.ship_to_id)
            != int(original.ship_to_id)
            or int(row.product_id)
            != int(original.product_id)
        ):
            raise ValueError(
                f"Relationship mismatch: "
                f"{row.transaction_id}"
            )

        return_date = date.fromisoformat(
            row.posting_date
        )

        shipment_date = date.fromisoformat(
            original.posting_date
        )

        if not (
            shipment_date < return_date
            <= LAST_POSTING_DATE
        ):
            raise ValueError(
                "Invalid return posting date."
            )

        validated_total += abs(amount)

    if validated_total != return_total:
        raise ValueError(
            "Return reconciliation failed."
        )

    difference = abs(
        return_total - RETURN_TARGET
    )

    if difference > (
        RETURN_TARGET * TARGET_TOLERANCE
    ):
        raise ValueError(
            "Returned merchandise outside "
            "the modeled tolerance."
        )


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "Generating January–September 2026 ERP Returns"
    )
    print("-" * 65)

    if OUTPUT_PATH.exists():
        raise FileExistsError(
            "Output already exists: "
            + str(OUTPUT_PATH)
        )

    shipments = load_shipments()

    records, return_total = generate_returns(
        shipments
    )

    returns = pd.DataFrame(records)

    validate_returns(
        returns,
        shipments,
        return_total,
    )

    returns = returns.sort_values(
        ["posting_date", "transaction_id"]
    ).reset_index(drop=True)

    returns["source_row_number"] = (
        returns.groupby(
            "source_file_name"
        ).cumcount() + 1
    )

    shipment_total = sum(
        (
            Decimal(value)
            for value in shipments[
                "posted_sales_amount"
            ]
        ),
        Decimal("0.00"),
    )

    net_sales = (
        shipment_total - return_total
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Exclusive creation protects existing files.
    with OUTPUT_PATH.open(
        "x",
        encoding="utf-8",
    ) as file:
        returns.to_csv(
            file,
            index=False,
        )

    print(
        f"\nOriginal shipment lines: "
        f"{len(shipments):,}"
    )

    print(
        f"Return transactions: "
        f"{len(returns):,}"
    )

    print(
        f"Returned merchandise: "
        f"${return_total:,.2f}"
    )

    print(
        f"\nGross shipment revenue: "
        f"${shipment_total:,.2f}"
    )

    print(
        f"Net posted revenue: "
        f"${net_sales:,.2f}"
    )

    print(
        "Return rate: "
        f"{return_total / shipment_total * 100:.4f}%"
    )

    print(
        "\nPASS: 2026 return transactions validated."
    )

    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
