
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

YEAR = 2025
AVERAGE_LINE_TARGET = 1200
EXPECTED_FACILITIES = 5000
EXPECTED_PRODUCTS = 1200

# Results from our successful January prototype.
JANUARY_BASELINE_LINES = 30470
JANUARY_BASELINE_SALES = Decimal("33575057.52")


def round_decimal(value, places):
    """Round using exact decimal half-up rules."""
    precision = Decimal("1").scaleb(-places)
    return Decimal(str(value)).quantize(
        precision,
        rounding=ROUND_HALF_UP,
    )


def load_source_data():
    """Load and validate existing generation inputs."""
    monthly = pd.read_csv(
        DATA_DIR / "monthly_sales_profiles_2025.csv",
        dtype={
            "ship_to_id": int,
            "customer_id": int,
            "zip_code": str,
            "monthly_sales_target_2025": str,
        },
    )

    products = pd.read_csv(DATA_DIR / "products.csv")

    prices = pd.read_csv(
        DATA_DIR / "product_prices.csv",
        dtype={"base_unit_price": str},
    )

    ship_tos = pd.read_csv(
        DATA_DIR / "ship_tos.csv",
        dtype={
            "ship_to_id": int,
            "customer_id": int,
            "zip_code": str,
        },
    )

    if len(monthly) != EXPECTED_FACILITIES * 12:
        raise ValueError("Incomplete 2025 monthly profiles.")

    if monthly.duplicated(
        ["ship_to_id", "reporting_month"]
    ).any():
        raise ValueError("Duplicate facility-month profiles.")

    if len(ship_tos) != EXPECTED_FACILITIES:
        raise ValueError("Unexpected ship-to master count.")

    if ship_tos["ship_to_id"].duplicated().any():
        raise ValueError("Duplicate ship-to IDs.")

    # Verify facility ownership against the master data.
    checked = monthly.merge(
        ship_tos,
        on="ship_to_id",
        how="left",
        suffixes=("", "_master"),
        validate="many_to_one",
    )

    if checked["customer_id_master"].isna().any():
        raise ValueError("Unknown ship-to facility.")

    if not checked["customer_id"].eq(
        checked["customer_id_master"]
    ).all():
        raise ValueError("Customer and ship-to mismatch.")

    if not checked["zip_code"].eq(
        checked["zip_code_master"]
    ).all():
        raise ValueError("Ship-to ZIP mismatch.")

    catalog = products.merge(
        prices,
        on="product_id",
        validate="one_to_one",
    )

    if len(catalog) != EXPECTED_PRODUCTS:
        raise ValueError("Incomplete product catalog.")

    if catalog["product_id"].duplicated().any():
        raise ValueError("Duplicate catalog product IDs.")

    catalog["price_numeric"] = (
        catalog["base_unit_price"].astype(float)
    )

    catalog = catalog.sort_values(
        "price_numeric"
    ).reset_index(drop=True)

    if catalog["price_numeric"].le(0).any():
        raise ValueError("Invalid base selling price.")

    return monthly, catalog


def generate_month(month, monthly, catalog):
    """Generate one month of posted ERP shipment lines."""
    reporting_month = f"{YEAR}-{month:02d}"
    period_id = f"{YEAR}{month:02d}"

    # Separate, reproducible random state for every month.
    rng = np.random.default_rng(202500 + month)

    last_day = monthrange(YEAR, month)[1]

    period = monthly.loc[
        monthly["reporting_month"] == reporting_month
    ].copy()

    if len(period) != EXPECTED_FACILITIES:
        raise ValueError(
            f"Incomplete profiles for {reporting_month}."
        )

    period["target_cents"] = period[
        "monthly_sales_target_2025"
    ].map(
        lambda value: int(round_decimal(value, 2) * 100)
    )

    active = period.loc[
        period["target_cents"] > 0
    ].copy()

    price_array = catalog["price_numeric"].to_numpy()

    records = []
    transaction_counter = 0
    order_counter = 0
    partial_shipment_count = 0

    for facility in active.itertuples(index=False):
        monthly_target = (
            Decimal(int(facility.target_cents))
            / Decimal("100")
        )

        line_count = max(
            1,
            int(
                round(
                    float(monthly_target)
                    / AVERAGE_LINE_TARGET
                )
            ),
        )

        lines_created = 0

        while lines_created < line_count:
            order_counter += 1

            remaining_lines = line_count - lines_created
            order_line_count = min(
                int(rng.integers(1, 5)),
                remaining_lines,
            )

            order_number = (
                f"SO-{period_id}-{order_counter:07d}"
            )

            shipment_base = (
                f"SHP-{period_id}-{order_counter:07d}"
            )

            order_day = int(
                rng.integers(1, last_day + 1)
            )

            for order_line in range(
                1, order_line_count + 1
            ):
                lines_created += 1

                quantity = int(rng.integers(1, 7))

                desired_price = (
                    float(monthly_target)
                    / line_count
                    / quantity
                )

                nearest = int(
                    np.searchsorted(
                        price_array,
                        desired_price,
                    )
                )

                lower = max(0, nearest - 10)
                upper = min(
                    len(catalog),
                    nearest + 11,
                )

                selected_index = int(
                    rng.integers(lower, upper)
                )

                product = catalog.iloc[selected_index]

                base_price = Decimal(
                    product["base_unit_price"]
                )

                multiplier = Decimal(
                    str(rng.uniform(0.95, 1.05))
                )

                unit_price = round_decimal(
                    base_price * multiplier,
                    4,
                )

                # Some order lines are shipped in two parts.
                is_partial = (
                    quantity >= 2
                    and rng.random() < 0.10
                )

                if is_partial:
                    first_quantity = int(
                        rng.integers(1, quantity)
                    )

                    shipment_quantities = [
                        first_quantity,
                        quantity - first_quantity,
                    ]

                    first_day = min(
                        order_day,
                        last_day - 1,
                    )

                    second_day = min(
                        last_day,
                        first_day
                        + int(rng.integers(1, 4)),
                    )

                    shipment_days = [
                        first_day,
                        second_day,
                    ]

                    partial_shipment_count += 1

                else:
                    shipment_quantities = [quantity]
                    shipment_days = [order_day]

                for shipment_index, (
                    shipped_quantity,
                    posting_day,
                ) in enumerate(
                    zip(
                        shipment_quantities,
                        shipment_days,
                    ),
                    start=1,
                ):
                    transaction_counter += 1

                    posted_amount = round_decimal(
                        Decimal(shipped_quantity)
                        * unit_price,
                        2,
                    )

                    records.append({
                        "transaction_id": (
                            f"TXN-{period_id}-"
                            f"{transaction_counter:08d}"
                        ),
                        "transaction_type": "SHIPMENT",
                        "posting_date": (
                            f"{reporting_month}-"
                            f"{posting_day:02d}"
                        ),
                        "sales_order_number": order_number,
                        "sales_order_line": order_line,
                        "shipment_number": (
                            f"{shipment_base}-"
                            f"{shipment_index:02d}"
                        ),
                        "shipment_line": order_line,
                        "customer_id": int(
                            facility.customer_id
                        ),
                        "ship_to_id": int(
                            facility.ship_to_id
                        ),
                        "product_id": int(
                            product["product_id"]
                        ),
                        "quantity": (
                            f"{shipped_quantity:.3f}"
                        ),
                        "unit_selling_price": (
                            f"{unit_price:.4f}"
                        ),
                        "posted_sales_amount": (
                            f"{posted_amount:.2f}"
                        ),
                        "currency_code": "USD",
                        "reference_transaction_id": "",
                        "source_file_name": (
                            f"erp_sales_{YEAR}_{month:02d}.csv"
                        ),
                        "source_row_number": (
                            transaction_counter
                        ),
                        "load_batch_id": (
                            f"GEN-{period_id}"
                        ),
                    })

    result = pd.DataFrame(records)

    if result.empty:
        raise ValueError(
            f"No transactions for {reporting_month}."
        )

    # Structural validation.
    if not result["transaction_id"].is_unique:
        raise ValueError("Duplicate transaction IDs.")

    if not result["posting_date"].str.startswith(
        reporting_month
    ).all():
        raise ValueError("Incorrect posting month.")

    if not result["transaction_type"].eq(
        "SHIPMENT"
    ).all():
        raise ValueError("Unexpected transaction type.")

    if not result["product_id"].isin(
        catalog["product_id"]
    ).all():
        raise ValueError("Unknown product ID.")

    if not result["ship_to_id"].isin(
        period["ship_to_id"]
    ).all():
        raise ValueError("Unknown shipping facility.")

    # Reconcile every posted amount to quantity * price.
    total_sales = Decimal("0")

    for row in result.itertuples(index=False):
        quantity = Decimal(row.quantity)
        unit_price = Decimal(row.unit_selling_price)
        amount = Decimal(row.posted_sales_amount)

        if quantity <= 0 or unit_price <= 0:
            raise ValueError("Invalid shipment quantity or price.")

        expected = round_decimal(
            quantity * unit_price,
            2,
        )

        if amount != expected:
            raise ValueError(
                f"Amount mismatch: {row.transaction_id}"
            )

        total_sales += amount

    monthly_target = sum(
        (
            Decimal(value)
            for value in period[
                "monthly_sales_target_2025"
            ]
        ),
        Decimal("0"),
    )

    # Ensure January remains consistent with our baseline.
    if month == 1:
        if len(result) != JANUARY_BASELINE_LINES:
            raise ValueError(
                "January shipment count changed from baseline."
            )

        if total_sales != JANUARY_BASELINE_SALES:
            raise ValueError(
                "January sales changed from baseline."
            )

    # Save only after validation passes.
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    output_path = (
        RAW_DIR / f"erp_sales_{YEAR}_{month:02d}.csv"
    )

    result.to_csv(output_path, index=False)

    variance = total_sales - monthly_target

    print(
        f"{reporting_month} | "
        f"{len(result):>7,} lines | "
        f"${total_sales:>14,.2f} sales | "
        f"${variance:>12,.2f} variance"
    )

    return {
        "reporting_month": reporting_month,
        "shipment_lines": len(result),
        "sales_orders": order_counter,
        "partial_order_lines": partial_shipment_count,
        "shipment_sales": total_sales,
        "purchasing_target": monthly_target,
        "variance": variance,
    }


def main():
    print("Generating Full-Year 2025 ERP Shipments")
    print("-" * 75)

    monthly, catalog = load_source_data()

    results = []

    for month in range(1, 13):
        results.append(
            generate_month(month, monthly, catalog)
        )

    total_lines = sum(
        item["shipment_lines"] for item in results
    )

    total_orders = sum(
        item["sales_orders"] for item in results
    )

    total_partials = sum(
        item["partial_order_lines"] for item in results
    )

    total_sales = sum(
        (
            item["shipment_sales"]
            for item in results
        ),
        Decimal("0"),
    )

    total_target = sum(
        (
            item["purchasing_target"]
            for item in results
        ),
        Decimal("0"),
    )

    variance = total_sales - total_target

    if total_target != Decimal("500000000.00"):
        raise ValueError(
            "Annual purchasing target does not equal $500M."
        )

    print("\nFull-Year 2025 Summary")
    print("-" * 45)

    print(f"Monthly ERP exports: {len(results)}")
    print(f"Posted shipment lines: {total_lines:,}")
    print(f"Sales orders: {total_orders:,}")
    print(f"Partial order lines: {total_partials:,}")

    print(f"\nAnnual purchasing target: ${total_target:,.2f}")
    print(f"Generated shipment sales: ${total_sales:,.2f}")
    print(f"Difference from target: ${variance:,.2f}")

    print(
        "\nPASS: All 12 months generated "
        "with validated shipment amounts."
    )

    print(f"Files saved in: {RAW_DIR}")


if __name__ == "__main__":
    main()
