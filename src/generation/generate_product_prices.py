
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "processed"
RANDOM_SEED = 2026

# Fictional unit-price ranges by product family ID.
# Family IDs follow generate_products.py.
PRICE_RANGES = {
    1: (15, 400),       # Bearings
    2: (150, 8000),     # Electric Motors
    3: (300, 12000),    # Gearboxes & Reducers
    4: (12, 700),       # Belts & Pulleys
    5: (20, 1200),      # Chains & Sprockets
    6: (25, 900),       # Couplings & Bushings
    7: (40, 900),       # Sensors & Switches
    8: (200, 6000),     # PLCs & Controllers
    9: (250, 9000),     # Variable Frequency Drives
    10: (15, 1500),     # Contactors & Relays
    11: (2, 25),        # Industrial Wiring (per foot)
    12: (100, 5000),    # Control Panels & Enclosures
    13: (40, 3000),     # Conveyor Components
    14: (15, 900),      # Casters & Wheels
    15: (250, 15000),   # Lifting Equipment
    16: (200, 10000),   # Pallet Handling Equipment
    17: (100, 5000),    # Racking & Storage
    18: (10, 850),      # Material Handling Accessories
    19: (12, 350),      # Industrial Lubricants
    20: (8, 150),       # Fasteners & Hardware (per box)
    21: (10, 450),      # Safety & PPE
    22: (8, 300),       # Industrial Cleaning
    23: (15, 750),      # Hand Tools
    24: (8, 250),       # Adhesives & Sealants
}


def main():
    print("Generating Synthetic Product Selling Prices")
    print("-" * 48)

    products = pd.read_csv(DATA_DIR / "products.csv")

    if len(products) != 1200:
        raise ValueError("Expected 1,200 products.")

    if products["product_id"].duplicated().any():
        raise ValueError("Duplicate product IDs.")

    if set(products["family_id"]) != set(PRICE_RANGES):
        raise ValueError("Product families do not match pricing ranges.")

    rng = np.random.default_rng(RANDOM_SEED)

    price_rows = []

    for product in products.itertuples(index=False):
        minimum, maximum = PRICE_RANGES[product.family_id]

        # Log-uniform distribution provides more lower-priced
        # products and fewer expensive specialty items.
        base_price = float(
            np.exp(rng.uniform(np.log(minimum), np.log(maximum)))
        )

        price_rows.append({
            "product_id": product.product_id,
            "base_unit_price": round(base_price, 4),
            "currency_code": "USD",
        })

    prices = pd.DataFrame(price_rows)

    if prices["base_unit_price"].le(0).any():
        raise ValueError("Generated nonpositive prices.")

    if prices["product_id"].duplicated().any():
        raise ValueError("Duplicate product pricing records.")

    output_path = DATA_DIR / "product_prices.csv"
    prices.to_csv(output_path, index=False, float_format="%.4f")

    print(f"\nProducts priced: {len(prices):,}")
    print(f"Minimum base price: ${prices['base_unit_price'].min():,.2f}")
    print(f"Maximum base price: ${prices['base_unit_price'].max():,.2f}")
    print(f"Average base price: ${prices['base_unit_price'].mean():,.2f}")

    print("\nSample pricing by family:")
    summary = (
        prices.merge(
            products[["product_id", "family_id"]],
            on="product_id",
        )
        .groupby("family_id")["base_unit_price"]
        .agg(["min", "median", "max"])
        .round(2)
    )
    print(summary.head(10).to_string())

    print("\nPASS: Synthetic product prices generated.")
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
