
from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

YEAR = 2026
MONTHS = range(1, 10)

EXPECTED_FACILITIES = 5000
EXPECTED_PRODUCTS = 1200
AVERAGE_LINE_TARGET = 1200

RANDOM_SEED = 2026


def round_decimal(value, places):
    precision = Decimal("1").scaleb(-places)
    return Decimal(str(value)).quantize(
        precision,
        rounding=ROUND_HALF_UP,
    )


def money_to_cents(value):
    return int(round_decimal(value, 2) * 100)


# ============================================================
# LOAD EXISTING MASTER DATA
# ============================================================

def load_source_data():
    monthly = pd.read_csv(
        DATA_DIR / "monthly_sales_profiles_2025.csv",
        dtype={
            "ship_to_id": int,
            "customer_id": int,
            "zip_code": str,
            "reporting_month": str,
            "monthly_sales_target_2025": str,
        },
    )

    ship_tos = pd.read_csv(
        DATA_DIR / "ship_tos.csv",
        dtype={
            "ship_to_id": int,
            "customer_id": int,
            "zip_code": str,
        },
    )

    products = pd.read_csv(
        DATA_DIR / "products.csv"
    )

    prices = pd.read_csv(
        DATA_DIR / "product_prices.csv",
        dtype={"base_unit_price": str},
    )

    if len(ship_tos) != EXPECTED_FACILITIES:
        raise ValueError("Unexpected ship-to master count.")

    if ship_tos["ship_to_id"].duplicated().any():
        raise ValueError("Duplicate ship-to IDs.")

    if len(monthly) != EXPECTED_FACILITIES * 12:
        raise ValueError("Incomplete 2025 monthly profiles.")

    if monthly.duplicated(
        ["ship_to_id", "reporting_month"]
    ).any():
        raise ValueError("Duplicate facility-month profiles.")

    expected_months = {
        f"2025-{month:02d}" for month in range(1, 13)
    }

    if set(monthly["reporting_month"]) != expected_months:
        raise ValueError("Unexpected 2025 reporting months.")

    checked = monthly.merge(
        ship_tos[
            ["ship_to_id", "customer_id", "zip_code"]
        ],
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
        raise ValueError("Customer/ship-to mismatch.")

    if not checked["zip_code"].eq(
        checked["zip_code_master"]
    ).all():
        raise ValueError("Shipping ZIP mismatch.")

    catalog = products.merge(
        prices,
        on="product_id",
        validate="one_to_one",
    )

    if len(catalog) != EXPECTED_PRODUCTS:
        raise ValueError("Incomplete product catalog.")

    if catalog["product_id"].duplicated().any():
        raise ValueError("Duplicate product IDs.")

    catalog["price_numeric"] = pd.to_numeric(
        catalog["base_unit_price"],
        errors="raise",
    )

    if (
        ~np.isfinite(
            catalog["price_numeric"].to_numpy()
        )
    ).any():
        raise ValueError("Invalid product price.")

    if catalog["price_numeric"].le(0).any():
        raise ValueError("Nonpositive product price.")

    catalog = catalog.sort_values(
        "price_numeric"
    ).reset_index(drop=True)

    return monthly, catalog


# ============================================================
# BUILD 2026 PURCHASING PROFILES
# ============================================================

def build_2026_profiles(monthly):
    """
    Reuse the established 2025 purchasing patterns.

    Each parent customer receives one reproducible
    annual change, with modest facility variation.

    No customer IDs, facility IDs, or ZIP codes
    are regenerated.
    """
    rng = np.random.default_rng(RANDOM_SEED)

    profiles = monthly[
        monthly["reporting_month"].str.endswith(
            tuple(f"-{m:02d}" for m in MONTHS)
        )
    ].copy()

    customers = sorted(
        profiles["customer_id"].unique()
    )

    facilities = sorted(
        profiles["ship_to_id"].unique()
    )

    customer_growth = {
        customer_id: float(
            np.clip(
                rng.normal(0.055, 0.085),
                -0.25,
                0.35,
            )
        )
        for customer_id in customers
    }

    facility_variation = {
        ship_to_id: float(
            np.clip(
                rng.normal(0.0, 0.035),
                -0.10,
                0.10,
            )
        )
        for ship_to_id in facilities
    }

    profiles["growth_rate"] = (
        profiles["customer_id"].map(
            customer_growth
        )
    )

    profiles["facility_variation"] = (
        profiles["ship_to_id"].map(
            facility_variation
        )
    )

    profiles["target_2026_cents"] = [
        money_to_cents(
            Decimal(value)
            * Decimal(
                str(
                    1.0 + growth + variation
                )
            )
        )
        for value, growth, variation in zip(
            profiles["monthly_sales_target_2025"],
            profiles["growth_rate"],
            profiles["facility_variation"],
        )
    ]

    if profiles["target_2026_cents"].lt(0).any():
        raise ValueError("Negative monthly sales target.")

    profiles["reporting_month"] = (
        profiles["reporting_month"].str.replace(
            "2025-",
            "2026-",
            regex=False,
        )
    )

    if len(profiles) != EXPECTED_FACILITIES * 9:
        raise ValueError(
            "Incomplete 2026 facility-month profiles."
        )

    return profiles


# ============================================================
# GENERATE ONE MONTH OF ERP SHIPMENTS
# ============================================================

def generate_month(month, profiles, catalog):
    reporting_month = f"{YEAR}-{month:02d}"
    period_id = f"{YEAR}{month:02d}"

    rng = np.random.default_rng(
        YEAR * 100 + month
    )

    last_day = monthrange(YEAR, month)[1]

    period = profiles.loc[
        profiles["reporting_month"] == reporting_month
    ].copy()

    if len(period) != EXPECTED_FACILITIES:
        raise ValueError(
            f"Incomplete profiles for {reporting_month}."
        )

    active = period.loc[
        period["target_2026_cents"] > 0
    ]

    price_array = catalog[
        "price_numeric"
    ].to_numpy()

    records = []

    transaction_counter = 0
    order_counter = 0
    partial_count = 0

    for facility in active.itertuples(index=False):
        monthly_target = (
            Decimal(int(facility.target_2026_cents))
            / Decimal(100)
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

            remaining = line_count - lines_created

            order_line_count = min(
                int(rng.integers(1, 5)),
                remaining,
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

                quantity = int(
                    rng.integers(1, 7)
                )

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

                product = catalog.iloc[
                    selected_index
                ]

                base_price = Decimal(
                    str(product["base_unit_price"])
                )

                multiplier = Decimal(
                    str(
                        rng.uniform(0.95, 1.05)
                    )
                )

                unit_price = round_decimal(
                    base_price * multiplier,
                    4,
                )

                is_partial = (
                    quantity >= 2
                    and rng.random() < 0.10
                )

                if is_partial:
                    first_quantity = int(
                        rng.integers(1, quantity)
                    )

                    quantities = [
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

                    posting_days = [
                        first_day,
                        second_day,
                    ]

                    partial_count += 1

                else:
                    quantities = [quantity]
                    posting_days = [order_day]

                for shipment_index, (
                    shipped_quantity,
                    posting_day,
                ) in enumerate(
                    zip(
                        quantities,
                        posting_days,
                    ),
                    start=1,
                ):
                    transaction_counter += 1

                    amount = round_decimal(
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
                            f"{amount:.2f}"
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

    if not result["transaction_id"].is_unique:
        raise ValueError("Duplicate transaction IDs.")

    if not result["posting_date"].str.startswith(
        reporting_month
    ).all():
        raise ValueError("Incorrect posting month.")

    if not result["transaction_type"].eq(
        "SHIPMENT"
    ).all():
        raise ValueError("Invalid transaction type.")

    if not result["product_id"].isin(
        catalog["product_id"]
    ).all():
        raise ValueError("Unknown product ID.")

    facility_relationships = period[
        ["ship_to_id", "customer_id"]
    ].drop_duplicates()

    checked = result[
        ["ship_to_id", "customer_id"]
    ].merge(
        facility_relationships,
        on="ship_to_id",
        how="left",
        suffixes=("", "_master"),
        validate="many_to_one",
    )

    if (
        checked["customer_id_master"].isna().any()
        or not checked["customer_id"].eq(
            checked["customer_id_master"]
        ).all()
    ):
        raise ValueError(
            "Generated transaction relationship mismatch."
        )

    total_cents = 0

    for row in result.itertuples(index=False):
        quantity = Decimal(row.quantity)
        unit_price = Decimal(row.unit_selling_price)
        amount = Decimal(row.posted_sales_amount)

        if quantity <= 0 or unit_price <= 0:
            raise ValueError(
                "Invalid shipment quantity or price."
            )

        expected = round_decimal(
            quantity * unit_price,
            2,
        )

        if expected != amount:
            raise ValueError(
                f"Amount mismatch: {row.transaction_id}"
            )

        total_cents += int(amount * 100)

    target_cents = int(
        period["target_2026_cents"].sum()
    )

    return result, {
        "month": reporting_month,
        "lines": len(result),
        "orders": order_counter,
        "partials": partial_count,
        "sales_cents": total_cents,
        "target_cents": target_cents,
        "variance_cents": total_cents - target_cents,
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("Generating January–September 2026 ERP Shipments")
    print("-" * 70)

    monthly, catalog = load_source_data()

    profiles = build_2026_profiles(monthly)

    output_paths = [
        RAW_DIR / f"erp_sales_{YEAR}_{month:02d}.csv"
        for month in MONTHS
    ]

    existing = [
        str(path)
        for path in output_paths
        if path.exists()
    ]

    if existing:
        raise FileExistsError(
            "2026 output files already exist. "
            "No files were changed:\n"
            + "\n".join(existing)
        )

    results = []
    summaries = []

    for month in MONTHS:
        result, summary = generate_month(
            month,
            profiles,
            catalog,
        )

        results.append(result)
        summaries.append(summary)

        print(
            f"{summary['month']} | "
            f"{summary['lines']:,} lines | "
            f"${summary['sales_cents'] / 100:,.2f} sales | "
            f"${summary['variance_cents'] / 100:,.2f} "
            "variance"
        )

    all_ids = pd.concat(
        [
            frame["transaction_id"]
            for frame in results
        ],
        ignore_index=True,
    )

    if all_ids.duplicated().any():
        raise ValueError(
            "Duplicate transaction IDs across months."
        )

    total_lines = sum(
        row["lines"] for row in summaries
    )

    total_sales_cents = sum(
        row["sales_cents"] for row in summaries
    )

    total_target_cents = sum(
        row["target_cents"] for row in summaries
    )

    if total_sales_cents <= 0:
        raise ValueError("No 2026 shipment revenue.")

    # Preserve 2025 source profiles and ERP exports.
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    for month, frame in zip(MONTHS, results):
        path = (
            RAW_DIR / f"erp_sales_{YEAR}_{month:02d}.csv"
        )

        # Exclusive creation prevents accidental overwrite.
        with path.open("x", encoding="utf-8") as file:
            frame.to_csv(file, index=False)

    print("\nJanuary–September 2026 Summary")
    print("-" * 50)

    print(f"Monthly ERP exports: {len(results)}")
    print(f"Posted shipment lines: {total_lines:,}")

    print(
        "Modeled purchasing target: "
        f"${total_target_cents / 100:,.2f}"
    )

    print(
        "Generated shipment sales: "
        f"${total_sales_cents / 100:,.2f}"
    )

    print(
        "Variance: "
        f"${(total_sales_cents - total_target_cents) / 100:,.2f}"
    )

    print("\nPASS: 2026 shipment transactions validated.")
    print(f"Files saved in: {RAW_DIR}")


if __name__ == "__main__":
    main()
