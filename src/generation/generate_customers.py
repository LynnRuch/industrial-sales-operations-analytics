
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"

CUSTOMER_COUNT = 3000
SHIP_TO_COUNT = 5000
RANDOM_SEED = 2026

INDUSTRIES = [
    "Manufacturing",
    "Food Processing",
    "Automotive",
    "Construction Materials",
    "Packaging",
    "Warehousing & Distribution",
    "Industrial Equipment",
    "Chemicals",
    "Building Products",
    "Transportation Equipment",
]

NAME_PREFIXES = [
    "Northstar", "Summit", "Redstone", "Blue Ridge",
    "Ironwood", "Pinnacle", "Silver Creek", "Cedar",
    "Keystone", "Granite", "Riverton", "Clearwater",
    "Westbridge", "Oakridge", "Stonehaven", "Highland",
]

NAME_SUFFIXES = [
    "Industrial", "Manufacturing", "Products",
    "Systems", "Enterprises", "Solutions",
    "Industries", "Group",
]

FACILITY_TYPES = [
    "Manufacturing Plant",
    "Distribution Center",
    "Warehouse",
    "Service Facility",
    "Assembly Facility",
]


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    print("Generating Synthetic Customer Master Data")
    print("-" * 45)

    # Read the previously validated ZIP reference.
    zip_path = DATA_DIR / "us_zip_reference_2026.csv"
    zips = pd.read_csv(zip_path, dtype={"zip_code": str})

    if zips.empty or zips["zip_code"].duplicated().any():
        raise ValueError("ZIP reference is empty or contains duplicates.")

    zip_pool = zips["zip_code"].to_numpy()

    customer_ids = np.arange(1, CUSTOMER_COUNT + 1)

    segments = rng.choice(
        ["Small Business", "Mid-Market", "Enterprise"],
        size=CUSTOMER_COUNT,
        p=[0.55, 0.35, 0.10],
    )

    # Segment influences the probability of multiple locations.
    segment_weights = {
        "Small Business": 1,
        "Mid-Market": 3,
        "Enterprise": 8,
    }

    weights = np.array(
        [segment_weights[s] for s in segments],
        dtype=float,
    )
    weights /= weights.sum()

    name_prefix = rng.choice(NAME_PREFIXES, CUSTOMER_COUNT)
    name_suffix = rng.choice(NAME_SUFFIXES, CUSTOMER_COUNT)

    created_days = rng.integers(
        0, 365 * 14,
        size=CUSTOMER_COUNT,
    )

    customers = pd.DataFrame({
        "customer_id": customer_ids,
        "customer_name": [
            f"{a} {b} {customer_id:04d}"
            for a, b, customer_id in zip(
                name_prefix, name_suffix, customer_ids
            )
        ],
        "industry": rng.choice(INDUSTRIES, CUSTOMER_COUNT),
        "customer_segment": segments,
        "created_date": (
            pd.Timestamp("2010-01-01")
            + pd.to_timedelta(created_days, unit="D")
        ).strftime("%Y-%m-%d"),
    })

    # Guarantee one ship-to per parent customer.
    # Allocate remaining locations using segment weights.
    extra_locations = rng.choice(
        customer_ids,
        size=SHIP_TO_COUNT - CUSTOMER_COUNT,
        replace=True,
        p=weights,
    )

    ship_to_customer_ids = np.concatenate(
        [customer_ids, extra_locations]
    )

    rng.shuffle(ship_to_customer_ids)

    ship_to_ids = np.arange(1, SHIP_TO_COUNT + 1)

    # Repeated ZIPs are allowed: multiple companies can ship
    # to facilities in the same ZIP.
    assigned_zips = rng.choice(
        zip_pool,
        size=SHIP_TO_COUNT,
        replace=True,
    )

    ship_tos = pd.DataFrame({
        "ship_to_id": ship_to_ids,
        "customer_id": ship_to_customer_ids,
        "ship_to_name": [
            f"Facility {ship_to_id:05d}"
            for ship_to_id in ship_to_ids
        ],
        "zip_code": assigned_zips,
        "facility_type": rng.choice(
            FACILITY_TYPES, SHIP_TO_COUNT
        ),
        "active_flag": True,
    })

    # Validate customer and ship-to relationships.
    if len(customers) != CUSTOMER_COUNT:
        raise ValueError("Customer count mismatch.")

    if len(ship_tos) != SHIP_TO_COUNT:
        raise ValueError("Ship-to count mismatch.")

    if not ship_tos["customer_id"].isin(
        customers["customer_id"]
    ).all():
        raise ValueError("Invalid customer reference.")

    if not ship_tos["zip_code"].isin(
        zips["zip_code"]
    ).all():
        raise ValueError("Invalid ship-to ZIP reference.")

    if ship_tos["customer_id"].nunique() != CUSTOMER_COUNT:
        raise ValueError("Some customers have no ship-to locations.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    customers.to_csv(
        DATA_DIR / "customers.csv",
        index=False,
    )

    ship_tos.to_csv(
        DATA_DIR / "ship_tos.csv",
        index=False,
    )

    print(f"\nCustomers generated: {len(customers):,}")
    print(f"Ship-to facilities generated: {len(ship_tos):,}")
    print(
        "Customers with shipping facilities: "
        f"{ship_tos['customer_id'].nunique():,}"
    )
    print(
        "Unique shipping ZIPs: "
        f"{ship_tos['zip_code'].nunique():,}"
    )

    print("\nCustomer segments:")
    print(
        customers["customer_segment"]
        .value_counts()
        .to_string()
    )

    print("\nShip-to facilities per customer:")
    print(
        ship_tos.groupby("customer_id")
        .size()
        .describe()
        .round(2)
        .to_string()
    )

    print("\nPASS: Synthetic customer master data generated.")
    print("Files: data/processed/customers.csv")
    print("       data/processed/ship_tos.csv")


if __name__ == "__main__":
    main()
