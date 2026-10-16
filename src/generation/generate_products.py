
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

# Each category contains six product families.
# Each family contains 50 synthetic SKUs.
PRODUCT_HIERARCHY = {
    "Mechanical & Power Transmission": [
        ("Bearings", "EA"),
        ("Electric Motors", "EA"),
        ("Gearboxes & Reducers", "EA"),
        ("Belts & Pulleys", "EA"),
        ("Chains & Sprockets", "EA"),
        ("Couplings & Bushings", "EA"),
    ],
    "Electrical & Automation": [
        ("Sensors & Switches", "EA"),
        ("PLCs & Controllers", "EA"),
        ("Variable Frequency Drives", "EA"),
        ("Contactors & Relays", "EA"),
        ("Industrial Wiring", "FT"),
        ("Control Panels & Enclosures", "EA"),
    ],
    "Material Handling & Equipment": [
        ("Conveyor Components", "EA"),
        ("Casters & Wheels", "EA"),
        ("Lifting Equipment", "EA"),
        ("Pallet Handling Equipment", "EA"),
        ("Racking & Storage", "EA"),
        ("Material Handling Accessories", "EA"),
    ],
    "MRO": [
        ("Industrial Lubricants", "EA"),
        ("Fasteners & Hardware", "BOX"),
        ("Safety & PPE", "EA"),
        ("Industrial Cleaning", "EA"),
        ("Hand Tools", "EA"),
        ("Adhesives & Sealants", "EA"),
    ],
}

# Fictional variation labels for catalog demonstration.
VARIANTS = [
    "Standard",
    "Compact",
    "Heavy Duty",
    "High Efficiency",
    "Precision",
]


def main():
    print("Generating Synthetic Industrial Product Catalog")
    print("-" * 50)

    category_rows = []
    family_rows = []
    product_rows = []

    family_id = 0
    product_id = 0

    for category_id, (category_name, families) in enumerate(
        PRODUCT_HIERARCHY.items(), start=1
    ):
        category_rows.append({
            "category_id": category_id,
            "category_name": category_name,
        })

        for family_name, unit_of_measure in families:
            family_id += 1

            family_rows.append({
                "family_id": family_id,
                "category_id": category_id,
                "family_name": family_name,
            })

            for item_number in range(1, 51):
                product_id += 1

                variant = VARIANTS[(item_number - 1) % len(VARIANTS)]

                product_rows.append({
                    "product_id": product_id,
                    "sku": f"IND-{family_id:02d}-{item_number:03d}",
                    "product_name": (
                        f"{family_name} - {variant} "
                        f"Model {item_number:03d}"
                    ),
                    "family_id": family_id,
                    "unit_of_measure": unit_of_measure,
                    "active_flag": True,
                })

    categories = pd.DataFrame(category_rows)
    families = pd.DataFrame(family_rows)
    products = pd.DataFrame(product_rows)

    # Validate the generated hierarchy.
    assert len(categories) == 4
    assert len(families) == 24
    assert len(products) == 1200

    assert categories["category_id"].is_unique
    assert families["family_id"].is_unique
    assert products["product_id"].is_unique
    assert products["sku"].is_unique

    assert families["category_id"].isin(
        categories["category_id"]
    ).all()

    assert products["family_id"].isin(
        families["family_id"]
    ).all()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    categories.to_csv(
        OUTPUT_DIR / "product_categories.csv", index=False
    )
    families.to_csv(
        OUTPUT_DIR / "product_families.csv", index=False
    )
    products.to_csv(
        OUTPUT_DIR / "products.csv", index=False
    )

    print(f"\nCategories generated: {len(categories):,}")
    print(f"Families generated: {len(families):,}")
    print(f"SKUs generated: {len(products):,}")

    print("\nProduct category distribution:")
    summary = (
        products.merge(families, on="family_id")
        .merge(categories, on="category_id")
        .groupby("category_name")
        .size()
    )
    print(summary.to_string())

    print("\nSample products:")
    print(
        products[
            ["sku", "product_name", "unit_of_measure"]
        ].head(10).to_string(index=False)
    )

    print("\nPASS: Product catalog generated successfully.")


if __name__ == "__main__":
    main()
