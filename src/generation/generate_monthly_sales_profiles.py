
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

RANDOM_SEED = 2025
MONTHS = np.arange(1, 13)

# Relative seasonal purchasing activity.
SEASONAL_WEIGHTS = np.array(
    [
        0.85,  # January
        0.90,  # February
        1.05,  # March
        1.10,  # April
        1.05,  # May
        1.00,  # June
        0.95,  # July
        1.00,  # August
        1.10,  # September
        1.15,  # October
        1.05,  # November
        0.80,  # December
    ]
)

# Number of purchasing months by customer segment.
ACTIVITY_MONTHS = {
    "Small Business": (2, 8),
    "Mid-Market": (7, 12),
    "Enterprise": (10, 12),
}


def to_cents(value):
    """Convert a dollar amount into exact integer cents."""
    amount = Decimal(str(value))
    return int(
        (amount * 100).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def allocate_cents(total_cents, weights):
    """Allocate exact cents across purchasing months."""
    proportions = weights / weights.sum()

    raw = total_cents * proportions
    allocated = np.floor(raw).astype(np.int64)

    remainder = total_cents - int(allocated.sum())
    fractions = raw - allocated

    order = np.argsort(-fractions, kind="stable")
    allocated[order[:remainder]] += 1

    return allocated


def main():
    print("Generating 2025 Monthly Purchasing Profiles")
    print("-" * 48)

    rng = np.random.default_rng(RANDOM_SEED)

    # Load existing annual purchasing profiles.
    ship_tos = pd.read_csv(
        DATA_DIR / "ship_to_sales_profiles_2025.csv",
        dtype={
            "ship_to_id": int,
            "customer_id": int,
            "zip_code": str,
            "annual_sales_target_2025": str,
        },
    )

    customers = pd.read_csv(
        DATA_DIR / "customer_sales_profiles_2025.csv",
        usecols=["customer_id", "customer_segment"],
    )

    # Validate source records.
    if len(ship_tos) != 5000:
        raise ValueError("Expected 5,000 ship-to profiles.")

    if ship_tos["ship_to_id"].duplicated().any():
        raise ValueError("Duplicate ship-to IDs.")

    if customers["customer_id"].duplicated().any():
        raise ValueError("Duplicate parent customer IDs.")

    profiles = ship_tos.merge(
        customers,
        on="customer_id",
        how="left",
        validate="many_to_one",
    )

    if profiles["customer_segment"].isna().any():
        raise ValueError("Missing customer segments.")

    records = []

    # Distribute each facility's annual purchasing target across 12 months.
    for facility in profiles.itertuples(index=False):
        annual_cents = to_cents(facility.annual_sales_target_2025)
        monthly_cents = np.zeros(12, dtype=np.int64)

        if annual_cents > 0:
            minimum, maximum = ACTIVITY_MONTHS[
                facility.customer_segment
            ]

            active_count = int(
                rng.integers(minimum, maximum + 1)
            )

            # Select months using seasonal purchasing probabilities.
            selected_months = rng.choice(
                MONTHS,
                size=active_count,
                replace=False,
                p=SEASONAL_WEIGHTS / SEASONAL_WEIGHTS.sum(),
            )

            # Introduce variation between purchasing months.
            weights = (
                SEASONAL_WEIGHTS[selected_months - 1]
                * rng.lognormal(
                    mean=0.0,
                    sigma=0.35,
                    size=active_count,
                )
            )

            monthly_cents[selected_months - 1] = allocate_cents(
                annual_cents, weights
            )

        # Preserve zero-activity months for reporting.
        for month, cents in zip(MONTHS, monthly_cents):
            records.append(
                {
                    "ship_to_id": facility.ship_to_id,
                    "customer_id": facility.customer_id,
                    "zip_code": facility.zip_code,
                    "reporting_month": f"2025-{month:02d}",
                    "monthly_target_cents": int(cents),
                }
            )

    result = pd.DataFrame(records)

    # Validate expected facility-month coverage.
    if len(result) != 5000 * 12:
        raise ValueError("Unexpected monthly profile count.")

    if result["monthly_target_cents"].lt(0).any():
        raise ValueError("Negative monthly purchasing target.")

    # Reconcile each facility's monthly totals to its annual target.
    actual_totals = result.groupby(
        "ship_to_id"
    )["monthly_target_cents"].sum()

    expected_totals = pd.Series(
        {
            int(row.ship_to_id): to_cents(
                row.annual_sales_target_2025
            )
            for row in ship_tos.itertuples(index=False)
        },
        dtype="int64",
    )

    # Match by ship-to ID, not Series index names or row positions.
    comparison = pd.DataFrame(
        {
            "actual_cents": actual_totals,
            "expected_cents": expected_totals,
        }
    )

    comparison["difference_cents"] = (
        comparison["actual_cents"] - comparison["expected_cents"]
    )

    mismatches = comparison[
        comparison["difference_cents"].isna()
        | comparison["difference_cents"].ne(0)
    ]

    print(
        "\nFacilities with reconciliation differences: "
        f"{len(mismatches):,}"
    )

    if not mismatches.empty:
        print("\nFirst 10 mismatches:")
        print(mismatches.head(10).to_string())
        raise ValueError(
            "Monthly totals do not reconcile to annual targets."
        )

    # Reconcile the combined annual target to exactly $500 million.
    total_cents = int(expected_totals.sum())
    monthly_total_cents = int(result["monthly_target_cents"].sum())

    if total_cents != 50_000_000_000:
        raise ValueError(
            "Annual purchasing target is not $500 million."
        )

    if monthly_total_cents != total_cents:
        raise ValueError(
            "Combined monthly totals do not reconcile."
        )

    # Preserve exact two-decimal output in the CSV.
    result["monthly_sales_target_2025"] = (
        result["monthly_target_cents"].map(
            lambda cents: f"{cents // 100}.{cents % 100:02d}"
        )
    )

    # Summarize monthly totals using integer cents.
    monthly_summary = result.groupby(
        "reporting_month"
    )["monthly_target_cents"].sum()

    # Remove the temporary integer-cents column before saving.
    result = result.drop(columns=["monthly_target_cents"])

    output_path = DATA_DIR / "monthly_sales_profiles_2025.csv"
    result.to_csv(output_path, index=False)

    print(f"\nShipping facilities: {len(ship_tos):,}")
    print(f"Monthly profile records: {len(result):,}")
    print(f"Annual allocated target: ${total_cents / 100:,.2f}")

    print("\nMonthly purchasing targets:")
    for month, cents in monthly_summary.items():
        print(f"{month}: ${cents / 100:,.2f}")

    print(
        "\nPASS: Monthly targets reconcile exactly "
        "to annual targets."
    )
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
