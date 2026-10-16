
"""Build reproducible synthetic ZIP ownership from existing 2025 sales.

Default: read-only queries against the existing PostgreSQL database.
Offline test: --ship-tos CSV --transactions DIR [--zip-reference CSV].

Outputs are CSV files only; this script does not modify PostgreSQL.
Territories support sales attribution, not field-routing optimization.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SEED = 2026

# Transparent, adjustable planning assumptions, never ZIP/rep overrides.
FIELD_REVENUE_COVERAGE = 0.85
FIELD_REVENUE_GUIDE = 9_000_000
FIELD_CUSTOMER_GUIDE = 300
INSIDE_REVENUE_GUIDE = 15_000_000
INSIDE_CUSTOMER_GUIDE = 600
MAX_ITERATIONS = 8


def load_inputs(args):
    if args.ship_tos:
        ships = pd.read_csv(
            args.ship_tos,
            dtype={"zip_code": str}
        )
        files = sorted(
            Path(args.transactions).glob("erp_sales_2025_??.csv")
        )
        if len(files) != 12:
            raise ValueError(
                f"Expected 12 monthly ERP CSV files; found {len(files)}"
            )

        transaction_parts = []
        for file in files:
            part = pd.read_csv(
                file,
                usecols=[
                    "ship_to_id",
                    "customer_id",
                    "posted_sales_amount",
                    "transaction_type"
                ]
            )
            transaction_parts.append(part)

        tx = pd.concat(transaction_parts, ignore_index=True)

        if args.zip_reference:
            ref = pd.read_csv(
                args.zip_reference,
                dtype={"zip_code": str}
            )
        else:
            ref = ships[
                [
                    "zip_code",
                    "city",
                    "state_code",
                    "latitude",
                    "longitude"
                ]
            ].copy()
            ref = ref.drop_duplicates("zip_code")
            print(
                "OFFLINE TEST: Using ship-to ZIPs only; "
                "database mode covers all reference ZIPs."
            )
    else:
        from sqlalchemy import create_engine

        engine = create_engine(args.database_url)

        with engine.connect() as connection:
            ships = pd.read_sql(
                """
                SELECT
                    s.ship_to_id,
                    s.customer_id,
                    s.zip_code,
                    z.city,
                    z.state_code,
                    z.latitude,
                    z.longitude
                FROM core.ship_to s
                JOIN core.zip_reference z
                    ON s.zip_code = z.zip_code
                """,
                connection,
                dtype={"zip_code": str}
            )

            ref = pd.read_sql(
                """
                SELECT
                    zip_code,
                    city,
                    state_code,
                    latitude,
                    longitude
                FROM core.zip_reference
                """,
                connection,
                dtype={"zip_code": str}
            )

            tx = pd.read_sql(
                """
                SELECT
                    ship_to_id,
                    customer_id,
                    transaction_type,
                    posted_sales_amount
                FROM core.sales_transaction
                WHERE posting_date >= DATE '2025-01-01'
                  AND posting_date < DATE '2026-01-01'
                """,
                connection
            )

    return ships, ref, tx


# Verify shared identifiers and geography before any revenue-based assignments.
# Sales must join to the owning customer and receiving facility consistently.
def clean_inputs(ships, ref, tx):
    for name, frame, cols in [
        (
            "ship-to",
            ships,
            {"ship_to_id", "customer_id", "zip_code"}
        ),
        (
            "ZIP reference",
            ref,
            {"zip_code", "latitude", "longitude"}
        ),
        (
            "transaction",
            tx,
            {
                "ship_to_id",
                "customer_id",
                "posted_sales_amount"
            }
        ),
    ]:
        missing = cols.difference(frame.columns)
        if missing:
            raise ValueError(
                f"{name} missing columns: {sorted(missing)}"
            )

    if (
        ships.ship_to_id.duplicated().any()
        or ref.zip_code.duplicated().any()
    ):
        raise ValueError(
            "Duplicate ship-to IDs or ZIP reference IDs"
        )

    ships["zip_code"] = (
        ships.zip_code.astype(str).str.zfill(5)
    )
    ref["zip_code"] = (
        ref.zip_code.astype(str).str.zfill(5)
    )

    for coordinate in ["latitude", "longitude"]:
        ref[coordinate] = pd.to_numeric(
            ref[coordinate],
            errors="coerce"
        )

    if ref[
        ["latitude", "longitude"]
    ].isna().any().any():
        raise ValueError(
            "Missing ZIP reference coordinates"
        )

    if (
        ref.latitude.abs().gt(90).any()
        or ref.longitude.abs().gt(180).any()
    ):
        raise ValueError(
            "Invalid latitude or longitude"
        )

    if not set(ships.zip_code).issubset(
        set(ref.zip_code)
    ):
        raise ValueError(
            "Ship-to ZIP not present in ZIP reference"
        )

    links = tx.merge(
        ships[
            [
                "ship_to_id",
                "customer_id",
                "zip_code"
            ]
        ],
        on="ship_to_id",
        how="left",
        suffixes=("_tx", "_master"),
        validate="many_to_one"
    )

    if links.zip_code.isna().any():
        raise ValueError(
            "Transaction with missing ship-to record"
        )

    if (
        links.customer_id_tx
        != links.customer_id_master
    ).any():
        raise ValueError(
            "Transaction customer/ship-to relationship mismatch"
        )

    links["posted_sales_amount"] = pd.to_numeric(
        links.posted_sales_amount,
        errors="raise"
    )

    if not np.isfinite(
        links.posted_sales_amount.to_numpy()
    ).all():
        raise ValueError(
            "Nonfinite transaction revenue"
        )

    return links


# Form geographic clusters using reference-point coordinates and
# workload guidelines. These are attribution territories, not drive routes.
def allocate_market_zips(
    activities,
    selected,
    prefix,
    revenue_guide,
    customer_guide
):
    """Split geographic clusters according to demand and workload.

    KMeans uses unit-sphere coordinates to avoid longitude
    distortion. Revenue weighting emphasizes significant
    locations. State boundaries and mileage restrictions
    are not imposed.
    """
    subset = (
        activities.loc[selected]
        .copy()
        .sort_values("zip_code")
        .reset_index(drop=True)
    )

    if subset.empty:
        return (
            subset.assign(
                assigned_rep=pd.Series(dtype=str)
            ),
            pd.DataFrame()
        )

    lat = np.radians(
        subset.latitude.to_numpy(dtype=float)
    )
    lon = np.radians(
        subset.longitude.to_numpy(dtype=float)
    )

    xyz = np.column_stack([
        np.cos(lat) * np.cos(lon),
        np.cos(lat) * np.sin(lon),
        np.sin(lat)
    ])

    total_sales = max(
        0,
        float(subset.sales.sum())
    )

    # Seed the number of clusters using a revenue-per-rep planning guide.
    k = max(
        1,
        int(np.ceil(total_sales / revenue_guide))
    )
    k = min(k, len(subset))

    weights = (
        1.0
        + np.sqrt(
            np.maximum(
                subset.sales.to_numpy(), 0
            ) / 100_000
        )
    )

    # Increase cluster count only when the approximate revenue/customer
    # guides are exceeded. These thresholds are planning heuristics.
    for _ in range(MAX_ITERATIONS):
        model = KMeans(
            n_clusters=k,
            random_state=SEED,
            n_init=5,
            max_iter=150
        )

        labels = model.fit_predict(
            xyz,
            sample_weight=weights
        )

        subset["cluster"] = labels

        stats = subset.groupby(
            "cluster"
        ).agg(
            revenue=("sales", "sum"),
            customers_approx=(
                "zip_customers", "sum"
            )
        )

        if (
            stats.revenue.le(
                revenue_guide * 1.75
            )
            &
            stats.customers_approx.le(
                customer_guide * 1.30
            )
        ).all():
            break

        new_k = min(
            len(subset),
            k + max(
                1,
                int(np.ceil(k * 0.12))
            )
        )

        if new_k == k:
            break

        k = new_k

    # Assign stable representative IDs by geographic center order, rather
    # than by KMeans label values (which have no business meaning).
    centers = []

    for c, part in subset.groupby("cluster"):
        center = xyz[part.index].mean(axis=0)

        centers.append((
            c,
            float(
                np.arctan2(
                    center[1],
                    center[0]
                )
            ),
            float(
                np.arctan2(
                    center[2],
                    np.hypot(
                        center[0],
                        center[1]
                    )
                )
            )
        ))

    order = [
        c for c, _, _ in sorted(
            centers,
            key=lambda x: (x[2], x[1])
        )
    ]

    names = {
        cluster: f"{prefix}{i:03d}"
        for i, cluster in enumerate(order, 1)
    }

    subset["assigned_rep"] = (
        subset.cluster.map(names)
    )

    subset = subset.drop(columns="cluster")

    return (
        subset,
        pd.DataFrame({
            "rep_id": list(names.values()),
            "source_cluster": order
        })
    )


# Attribute 2025 net sales to the customer receiving ZIP and separate
# the higher-revenue field market from inside-sales coverage.
def build(ships, ref, links):
    # Sales credited by the ship-to ZIP.
    sales = links.groupby(
        "zip_code",
        as_index=False
    ).agg(
        sales=("posted_sales_amount", "sum")
    )

    customer_zips = ships[
        ["zip_code", "customer_id"]
    ].drop_duplicates()

    customers = customer_zips.groupby(
        "zip_code"
    ).size().rename("zip_customers")

    activity = ref.merge(
        sales,
        on="zip_code",
        how="left",
        validate="one_to_one"
    )

    activity = activity.merge(
        customers,
        on="zip_code",
        how="left",
        validate="one_to_one"
    )

    activity["sales"] = (
        activity.sales.fillna(0.0)
    )

    activity["zip_customers"] = (
        activity.zip_customers.fillna(0).astype(int)
    )

    positive = (
        activity.loc[activity.sales > 0]
        .sort_values(
            ["sales", "zip_code"],
            ascending=[False, True]
        )
        .copy()
    )

    if (
        positive.empty
        or positive.sales.sum() <= 0
    ):
        raise ValueError(
            "2025 sales contain no positive national revenue"
        )

    target = (
        positive.sales.sum()
        * FIELD_REVENUE_COVERAGE
    )

    # Include the highest-revenue ZIPs until the field-coverage target
    # is met; remaining reference ZIPs receive inside coverage.
    selected = positive.loc[
        positive.sales.cumsum().shift(
            fill_value=0
        ) < target,
        "zip_code"
    ]

    field_mask = (
        activity.zip_code.isin(selected)
    )

    field, _ = allocate_market_zips(
        activity,
        field_mask,
        "FLD",
        FIELD_REVENUE_GUIDE,
        FIELD_CUSTOMER_GUIDE
    )

    inside, _ = allocate_market_zips(
        activity,
        ~field_mask,
        "INS",
        INSIDE_REVENUE_GUIDE,
        INSIDE_CUSTOMER_GUIDE
    )

    assignments = pd.concat(
        [field, inside],
        ignore_index=True
    )

    assignments = assignments.rename(
        columns={
            "assigned_rep": "rep_id",
            "sales": "sales_2025"
        }
    )

    assignments["coverage_type"] = np.where(
        assignments.rep_id.str.startswith("FLD"),
        "Field",
        "Inside"
    )

    # Every reference ZIP must have exactly one owner; assignment
    # preserves the total 2025 transaction revenue.
    if (
        len(assignments) != len(ref)
        or assignments.zip_code.duplicated().any()
        or assignments.rep_id.isna().any()
    ):
        raise ValueError(
            "Ownership must be exactly one "
            "representative per reference ZIP"
        )

    if not np.isclose(
        assignments.sales_2025.sum(),
        links.posted_sales_amount.sum(),
        atol=0.01
    ):
        raise ValueError(
            "ZIP assignment revenue did not reconcile"
        )

    customer_ownership = customer_zips.merge(
        assignments[
            ["zip_code", "rep_id"]
        ],
        on="zip_code",
        validate="many_to_one"
    )

    rep_customers = (
        customer_ownership.groupby(
            "rep_id"
        ).customer_id.nunique()
        .rename("distinct_customers")
    )

    summary = assignments.groupby(
        ["rep_id", "coverage_type"],
        as_index=False
    ).agg(
        zip_count=("zip_code", "size"),
        active_zips=(
            "sales_2025",
            lambda s: int((s != 0).sum())
        ),
        revenue_2025=("sales_2025", "sum")
    )

    summary = summary.merge(
        rep_customers,
        on="rep_id",
        how="left",
        validate="one_to_one"
    )

    summary.distinct_customers = (
        summary.distinct_customers
        .fillna(0)
        .astype(int)
    )

    summary["customer_guideline_exception"] = np.where(
        summary.coverage_type.eq("Field"),
        summary.distinct_customers.gt(
            FIELD_CUSTOMER_GUIDE
        ),
        summary.distinct_customers.gt(
            INSIDE_CUSTOMER_GUIDE
        )
    )

    return assignments, summary


# The default run reads PostgreSQL and writes CSV artifacts only;
# the offline mode accepts the same inputs from validated local CSVs.
def main():
    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--database-url",
        default=(
            "postgresql+psycopg://postgres@localhost:5432/"
            "industrial_sales_ops_analytics"
        )
    )

    parser.add_argument(
        "--ship-tos",
        type=Path,
        help="Optional offline CSV input"
    )

    parser.add_argument(
        "--transactions",
        type=Path,
        help="Directory with 12 offline monthly ERP files"
    )

    parser.add_argument(
        "--zip-reference",
        type=Path,
        help="Optional offline ZIP reference CSV"
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=(
            PROJECT_ROOT
            / "data/processed/territory_assignments_v1"
        )
    )

    args = parser.parse_args()

    if bool(args.ship_tos) != bool(args.transactions):
        parser.error(
            "--ship-tos and --transactions "
            "must be supplied together"
        )

    ships, ref, tx = load_inputs(args)
    links = clean_inputs(ships, ref, tx)

    assignments, summary = build(
        ships,
        ref,
        links
    )

    if args.output.exists():
        raise FileExistsError(
            "Refusing to overwrite output directory: "
            f"{args.output}"
        )

    args.output.mkdir(parents=True)

    assignments[
        [
            "zip_code",
            "rep_id",
            "coverage_type",
            "city",
            "state_code",
            "latitude",
            "longitude",
            "sales_2025"
        ]
    ].sort_values("zip_code").to_csv(
        args.output / "zip_rep_assignments.csv",
        index=False
    )

    summary.sort_values(
        "rep_id"
    ).to_csv(
        args.output / "rep_territory_summary.csv",
        index=False
    )

    print(
        f"ZIPs assigned: {len(assignments):,}; "
        f"representatives: {len(summary)}"
    )

    print(
        f"Field: "
        f"{(summary.coverage_type == 'Field').sum()}; "
        f"Inside: "
        f"{(summary.coverage_type == 'Inside').sum()}"
    )

    print(
        "2025 revenue reconciled: "
        f"${assignments.sales_2025.sum():,.2f}"
    )

    print(
        "Customer guideline exceptions: "
        f"{summary.customer_guideline_exception.sum()}"
    )

    print(
        f"Outputs: {args.output.resolve()}"
    )


if __name__ == "__main__":
    main()
