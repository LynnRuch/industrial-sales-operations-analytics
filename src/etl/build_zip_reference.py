
from pathlib import Path
import zipfile

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

CENSUS_ARCHIVE = REFERENCE_DIR / "2026_Gaz_zcta_national.zip"
GEONAMES_ARCHIVE = REFERENCE_DIR / "US.zip"

CONTIGUOUS_STATES = {
    "AL", "AZ", "AR", "CA", "CO", "CT", "DE", "FL",
    "GA", "ID", "IL", "IN", "IA", "KS", "KY", "LA",
    "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
    "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND",
    "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

GEONAMES_COLUMNS = [
    "country_code",
    "zip_code",
    "city",
    "state",
    "state_code",
    "county",
    "county_code",
    "community",
    "community_code",
    "latitude",
    "longitude",
    "accuracy",
]


def main():
    print("Building Contiguous US ZIP Reference")
    print("-" * 45)

    with zipfile.ZipFile(CENSUS_ARCHIVE) as archive:
        with archive.open("2026_Gaz_zcta_national.txt") as source:
            census = pd.read_csv(
                source,
                sep="|",
                dtype=str,
                encoding="utf-8-sig",
            )

    census.columns = census.columns.str.strip()
    census = census.apply(lambda col: col.str.strip())

    with zipfile.ZipFile(GEONAMES_ARCHIVE) as archive:
        with archive.open("US.txt") as source:
            geonames = pd.read_csv(
                source,
                sep="\t",
                header=None,
                names=GEONAMES_COLUMNS,
                dtype=str,
            )

    geonames = geonames.apply(lambda col: col.str.strip())

    # Keep only contiguous US states and Washington, DC.
    geonames = geonames[
        geonames["state_code"].isin(CONTIGUOUS_STATES)
    ].copy()

    # Choose a consistent display city where duplicates exist.
    geonames = (
        geonames.sort_values(
            ["zip_code", "city"],
            kind="stable",
        )
        .drop_duplicates(subset=["zip_code"], keep="first")
    )

    # Match Census ZCTA geography with GeoNames descriptions.
    merged = census.merge(
        geonames[
            ["zip_code", "city", "state", "state_code", "county"]
        ],
        left_on="GEOID",
        right_on="zip_code",
        how="inner",
        validate="one_to_one",
    )

    result = merged[
        [
            "GEOID",
            "city",
            "state",
            "state_code",
            "county",
            "INTPTLAT",
            "INTPTLONG",
        ]
    ].copy()

    result.columns = [
        "zip_code",
        "city",
        "state_name",
        "state_code",
        "county",
        "latitude",
        "longitude",
    ]

    result["latitude"] = pd.to_numeric(result["latitude"])
    result["longitude"] = pd.to_numeric(result["longitude"])

    result = result.sort_values("zip_code").reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / "us_zip_reference_2026.csv"

    result.to_csv(output_path, index=False)

    print(f"\nCensus ZCTAs: {len(census):,}")
    print(f"GeoNames ZIPs after filtering: {len(geonames):,}")
    print(f"Matched ZIPs: {len(result):,}")
    print(f"Unmatched Census ZCTAs: {len(census) - len(result):,}")

    print("\nStates represented:")
    print(sorted(result["state_code"].unique()))

    print("\nMissing values:")
    print(result.isna().sum().to_string())

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
