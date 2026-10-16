
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

RANDOM_SEED = 2025
TARGET_ANNUAL_SALES = 500_000_000

# Relative purchasing potential by customer segment.
SEGMENT_MULTIPLIERS = {
    "Small Business": 1.0,
    "Mid-Market": 4.0,
    "Enterprise": 15.0,
}

INACTIVE_RATE = 0.05


def main():
    print("Generating 2025 Customer Purchasing Profiles")
    print("-" * 48)

    customers = pd.read_csv(DATA_DIR / "customers.csv")

    if len(customers) != 3000:
        raise ValueError("Expected 3,000 customers.")

    if customers["customer_id"].duplicated().any():
        raise ValueError("Duplicate customer IDs.")

    if not customers["customer_segment"].isin(
        SEGMENT_MULTIPLIERS
    ).all():
        raise ValueError("Unknown customer segment.")

    rng = np.random.default_rng(RANDOM_SEED)

    # Begin with segment-based purchasing potential.
    segment_weights = (
        customers["customer_segment"]
        .map(SEGMENT_MULTIPLIERS)
        .to_numpy(dtype=float)
    )

    # Introduce variation among customers in each segment.
    customer_variation = rng.lognormal(
        mean=0.0,
        sigma=0.9,
        size=len(customers),
    )

    purchasing_weights = segment_weights * customer_variation

    # Some customers have no 2025 purchasing activity.
    active_flags = rng.random(len(customers)) >= INACTIVE_RATE
    purchasing_weights[~active_flags] = 0.0

    if purchasing_weights.sum() <= 0:
        raise ValueError("No active customer purchasing potential.")

    # Scale potential sales across the active customer base.
    annual_targets = (
        purchasing_weights
        / purchasing_weights.sum()
        * TARGET_ANNUAL_SALES
    )

    profiles = customers[
        ["customer_id", "customer_segment"]
    ].copy()

    profiles["active_2025"] = active_flags
    profiles["annual_sales_target_2025"] = np.round(
        annual_targets, 2
    )

    # Correct rounding differences to reconcile the target.
    difference = round(
        TARGET_ANNUAL_SALES
        - profiles["annual_sales_target_2025"].sum(),
        2,
    )

    largest_customer = (
        profiles["annual_sales_target_2025"].idxmax()
    )

    profiles.loc[
        largest_customer, "annual_sales_target_2025"
    ] = round(
        profiles.loc[
            largest_customer, "annual_sales_target_2025"
        ] + difference,
        2,
    )

    if profiles["annual_sales_target_2025"].lt(0).any():
        raise ValueError("Negative customer sales target.")

    output_path = DATA_DIR / "customer_sales_profiles_2025.csv"

    profiles.to_csv(
        output_path,
        index=False,
        float_format="%.2f",
    )

    print(f"\nCustomer profiles: {len(profiles):,}")
    print(f"Active customers: {active_flags.sum():,}")
    print(f"Inactive customers: {(~active_flags).sum():,}")

    print(
        "Combined annual sales target: "
        f"${profiles['annual_sales_target_2025'].sum():,.2f}"
    )

    print("\nSales target distribution by segment:")
    summary = profiles.groupby("customer_segment").agg(
        customers=("customer_id", "count"),
        sales_target=("annual_sales_target_2025", "sum"),
        average_target=("annual_sales_target_2025", "mean"),
    )
    print(summary.round(2).to_string())

    print("\nTop five customer targets:")
    print(
        profiles.nlargest(
            5, "annual_sales_target_2025"
        ).to_string(index=False)
    )

    print("\nPASS: Customer purchasing profiles generated.")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
