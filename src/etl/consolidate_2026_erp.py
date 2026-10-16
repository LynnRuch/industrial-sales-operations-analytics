
"""Consolidate validated 2026 shipments and returns into monthly ERP extracts."""
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
OUTPUT = PROCESSED / "erp_2026_final"

EXPECTED_SHIPMENTS = 355_949
EXPECTED_RETURNS = 446
EXPECTED_NET = Decimal("392981461.96")

TEXT_COLUMNS = [
    "transaction_id", "posting_date", "quantity",
    "unit_selling_price", "posted_sales_amount",
    "reference_transaction_id", "source_file_name",
    "load_batch_id", "sales_order_number", "shipment_number",
]


# Read monetary and identifier fields as text to preserve decimal
# precision and leading zeros through reconciliation.
def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(path)

    return pd.read_csv(
        path,
        dtype={name: str for name in TEXT_COLUMNS},
        keep_default_na=False,
    )


def total_sales(frame):
    return sum(
        map(Decimal, frame["posted_sales_amount"]),
        Decimal("0.00"),
    )


# Validate signed quantities and line amounts for both shipments
# and returns using decimal arithmetic.
def check_amounts(frame):
    for row in frame.itertuples(index=False):
        qty = Decimal(row.quantity)
        price = Decimal(row.unit_selling_price)
        amount = Decimal(row.posted_sales_amount)

        calculated = (qty * price).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        if amount != calculated or price <= 0:
            raise ValueError(
                f"Invalid amount: {row.transaction_id}"
            )

        if row.transaction_type == "SHIPMENT":
            if qty <= 0 or amount <= 0:
                raise ValueError(
                    f"Invalid shipment: {row.transaction_id}"
                )

        elif row.transaction_type == "RETURN":
            if qty >= 0 or amount >= 0:
                raise ValueError(
                    f"Invalid return: {row.transaction_id}"
                )

        else:
            raise ValueError(
                f"Invalid transaction type: {row.transaction_id}"
            )


# Consolidate the nine 2026 shipment extracts with their returns.
# Nothing is written until the full set passes integrity checks.
def main():
    paths = [
        RAW / f"erp_sales_2026_{m:02d}.csv"
        for m in range(1, 10)
    ]

    if OUTPUT.exists() and any(OUTPUT.iterdir()):
        raise FileExistsError(
            f"Output folder is not empty: {OUTPUT}"
        )

    shipments = pd.concat(
        [read_csv(p) for p in paths],
        ignore_index=True,
    )

    returns = read_csv(
        PROCESSED / "2026_returns.csv"
    )

    if (
        len(shipments) != EXPECTED_SHIPMENTS
        or len(returns) != EXPECTED_RETURNS
    ):
        raise ValueError(
            "Shipment or return count differs "
            "from validated baseline"
        )

    if not shipments.transaction_type.eq(
        "SHIPMENT"
    ).all():
        raise ValueError(
            "Non-shipment in shipment input"
        )

    if not returns.transaction_type.eq(
        "RETURN"
    ).all():
        raise ValueError(
            "Non-return in returns input"
        )

    combined = pd.concat(
        [shipments, returns],
        ignore_index=True,
    )

    if not combined.transaction_id.is_unique:
        raise ValueError(
            "Duplicate transaction IDs"
        )

    if not combined.posting_date.str.match(
        r"^2026-(0[1-9])-[0-3][0-9]$"
    ).all():
        raise ValueError(
            "Posting date outside January–September 2026"
        )

    parsed_dates = pd.to_datetime(
        combined.posting_date,
        errors="raise",
    )

    if not (
        parsed_dates.dt.year.eq(2026)
        & parsed_dates.dt.month.between(1, 9)
    ).all():
        raise ValueError(
            "Invalid reporting date"
        )

    if not combined.currency_code.eq("USD").all():
        raise ValueError(
            "Unexpected currency"
        )

    if combined.transaction_id.eq("").any():
        raise ValueError(
            "Blank transaction ID"
        )

    # Returns must refer to a 2026 shipment and retain the original
    # customer, facility, product, order, and shipment identifiers.
    shipment_lookup = shipments.set_index(
        "transaction_id"
    )

    if not returns.reference_transaction_id.isin(
        shipment_lookup.index
    ).all():
        raise ValueError(
            "Return references unknown shipment"
        )

    if returns.reference_transaction_id.duplicated().any():
        raise ValueError(
            "More than one return references a shipment"
        )

    for ret in returns.itertuples(index=False):
        original = shipment_lookup.loc[
            ret.reference_transaction_id
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
            if str(getattr(ret, field)) != str(
                original[field]
            ):
                raise ValueError(
                    "Return relationship mismatch: "
                    f"{ret.transaction_id}"
                )

        if ret.posting_date <= original.posting_date:
            raise ValueError(
                f"Return before shipment: {ret.transaction_id}"
            )

        if abs(Decimal(ret.quantity)) > Decimal(
            original.quantity
        ):
            raise ValueError(
                f"Return exceeds shipment: {ret.transaction_id}"
            )

        if Decimal(
            ret.unit_selling_price
        ) != Decimal(
            original.unit_selling_price
        ):
            raise ValueError(
                f"Return price mismatch: {ret.transaction_id}"
            )

    check_amounts(combined)

    if total_sales(combined) != EXPECTED_NET:
        raise ValueError(
            "2026 net sales failed reconciliation"
        )

    # Build monthly posting-date extracts; a return belongs to its
    # posting month, not necessarily the shipment's original month.
    outputs = []

    for month in range(1, 10):
        period = f"2026-{month:02d}"
        filename = (
            f"erp_posted_sales_2026_{month:02d}.csv"
        )

        frame = combined.loc[
            combined.posting_date.str.startswith(period)
        ].copy()

        if frame.empty:
            raise ValueError(
                f"Missing transactions for {period}"
            )

        frame = frame.sort_values(
            ["posting_date", "transaction_id"]
        ).reset_index(drop=True)

        frame["source_file_name"] = filename
        frame["source_row_number"] = range(
            1, len(frame) + 1
        )

        outputs.append((filename, frame))

        print(
            f"{period}: {len(frame):,} rows | "
            f"${total_sales(frame):,.2f} net"
        )

    if sum(
        len(frame) for _, frame in outputs
    ) != len(combined):
        raise ValueError(
            "Monthly record counts do not reconcile"
        )

    if sum(
        (
            total_sales(frame)
            for _, frame in outputs
        ),
        Decimal("0.00"),
    ) != EXPECTED_NET:
        raise ValueError(
            "Monthly net sales do not reconcile"
        )

    # Only now create output files; refuse overwrites of prior exports.
    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    for filename, frame in outputs:
        with (
            OUTPUT / filename
        ).open(
            "x",
            encoding="utf-8",
            newline="",
        ) as file:
            frame.to_csv(file, index=False)

    print(
        f"\nPASS: 9 consolidated files; "
        f"{len(combined):,} transactions"
    )
    print(
        f"Net revenue: ${EXPECTED_NET:,.2f}"
    )
    print(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
