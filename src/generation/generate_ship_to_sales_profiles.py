
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

RANDOM_SEED = 2025
EXPECTED_CUSTOMERS = 3000
EXPECTED_SHIP_TOS = 5000


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
    """Allocate an amount without losing or creating cents."""
    proportions = weights / weights.sum()

    allocated = np.floor(
        total_cents * proportions
    ).astype(np.int64)

    remainder = total_cents - int(allocated.sum())

    # Give remaining cents to the largest fractional shares.
    fractional = total_cents * proportions - allocated
    order = np.argsort(-fractional, kind="stable")

    allocated[order[:remainder]] += 1

    return allocated


def main():
    print("Generating 2025 Ship-To Purchasing Profiles")
    print("-" * 48)

    customers = pd.read_csv(
        DATA_DIR / "customer_sales_profiles_2025.csv",
        dtype={
            "customer_id": int,
            "annual_sales_target_2025": str,
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

    if len(customers) != EXPECTED_CUSTOMERS:
        raise ValueError("Unexpected customer profile count.")

    if len(ship_tos) != EXPECTED_SHIP_TOS:
        raise ValueError("Unexpected ship-to count.")

    if customers["customer_id"].duplicated().any():
        raise ValueError("Duplicate customer IDs.")

    if ship_tos["ship_to_id"].duplicated().any():
        raise ValueError("Duplicate ship-to IDs.")

    if not ship_tos["customer_id"].isin(
        customers["customer_id"]
    ).all():
        raise ValueError("Unknown parent customer.")

    rng = np.random.default_rng(RANDOM_SEED)

    customer_targets = {
        int(row.customer_id): to_cents(
            row.annual_sales_target_2025
        )
        for row in customers.itertuples(index=False)
    }

    records = []

    # Preserve original parent-to-facility relationships.
    for customer_id, facilities in ship_tos.groupby(
        "customer_id", sort=True
    ):
        facilities = facilities.sort_values("ship_to_id")
        annual_cents = customer_targets[customer_id]

        # Larger facilities generally receive more activity.
        # Variation creates realistic differences between sites.
        weights = rng.lognormal(
            mean=0.0,
            sigma=0.8,
            size=len(facilities),
        )

        facility_cents = allocate_cents(
            annual_cents, weights
        )

        for facility, cents in zip(
            facilities.itertuples(index=False),
            facility_cents,
        ):
            records.append({
                "ship_to_id": facility.ship_to_id,
                "customer_id": customer_id,
                "zip_code": facility.zip_code,
                "annual_target_cents": int(cents),
            })

    profiles = pd.DataFrame(records)

    # Validate that parent totals reconcile exactly.
    allocated_by_customer = profiles.groupby(
        "customer_id"
    )["annual_target_cents"].sum()

    expected_by_customer = pd.Series(
        customer_targets, dtype="int64"
    )

    if not allocated_by_customer.equals(
        expected_by_customer
    ):
        raise ValueError(
            "Ship-to totals do not reconcile to parents."
        )

    if profiles["annual_target_cents"].lt(0).any():
        raise ValueError("Negative facility target.")

    # Convert integer cents to dollar strings for CSV output.
    profiles["annual_sales_target_2025"] = (
        profiles["annual_target_cents"]
        .map(lambda cents: f"{cents // 100}.{cents % 100:02d}")
    )

    profiles = profiles.drop(
        columns=["annual_target_cents"]
    )

    output_path = (
        DATA_DIR / "ship_to_sales_profiles_2025.csv"
    )

    profiles.to_csv(output_path, index=False)

    total_cents = sum(customer_targets.values())

    print(f"\nParent customers: {len(customers):,}")
    print(f"Shipping facilities: {len(profiles):,}")
    print(
        "Unique shipping ZIPs: "
        f"{profiles['zip_code'].nunique():,}"
    )
    print(
        "2025 allocated sales target: "
        f"${total_cents / 100:,.2f}"
    )

    print("\nTop five facilities by annual target:")
    top = profiles.copy()
    top["annual_sales_target_2025"] = (
        top["annual_sales_target_2025"].astype(float)
    )
    print(
        top.nlargest(
            5, "annual_sales_target_2025"
        ).to_string(index=False)
    )

    print(
        "\nPASS: All ship-to totals reconcile "
        "exactly to their parent customers."
    )
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
