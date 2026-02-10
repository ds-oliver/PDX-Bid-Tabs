#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _to_num(df: pd.DataFrame, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def main():
    parser = argparse.ArgumentParser(description="Build optional sheet-native pay item metrics table.")
    parser.add_argument("--facts_dir", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--emit_metrics", action="store_true", help="Emit fact_project_pay_item_metrics.csv (default off).")
    args = parser.parse_args()

    if not args.emit_metrics:
        print("Skipping metrics build; pass --emit_metrics to generate output.")
        return

    facts_dir = Path(args.facts_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    line_path = facts_dir / "fact_bid_item_price.csv"
    total_path = facts_dir / "fact_bid_schedule_total.csv"
    bidder_path = facts_dir / "dim_bidder.csv"

    if not line_path.exists() or not bidder_path.exists() or not total_path.exists():
        raise SystemExit("Required inputs missing: fact_bid_item_price.csv, fact_bid_schedule_total.csv, dim_bidder.csv")

    line = pd.read_csv(line_path, keep_default_na=False)
    totals = pd.read_csv(total_path, keep_default_na=False)
    bidder = pd.read_csv(bidder_path, keep_default_na=False)

    line = _to_num(line, ["unit_price", "total_price"])
    totals = _to_num(totals, ["schedule_total"])

    line = line.merge(bidder[["bidder_id", "bidder_type"]], on="bidder_id", how="left")
    contractors = line[line["bidder_type"] == "CONTRACTOR"].copy()
    contractors = contractors[contractors["unit_price"].notna()].copy()

    group_keys = ["project_id", "bid_schedule_id", "pay_item_id"]

    metric_core = contractors.groupby(group_keys, as_index=False).agg(
        avg_unit_price_3low=("unit_price", lambda s: s.nsmallest(3).mean()),
        median_unit_price=("unit_price", "median"),
        min_unit_price=("unit_price", "min"),
        num_bidders_valid=("bidder_id", "nunique"),
    )

    totals_with_type = totals.merge(bidder[["bidder_id", "bidder_type"]], on="bidder_id", how="left")
    totals_with_type = totals_with_type[totals_with_type["bidder_type"] == "CONTRACTOR"].copy()
    low_totals = totals_with_type[totals_with_type["schedule_total"].notna()].copy()
    low_totals = low_totals.sort_values(["project_id", "bid_schedule_id", "schedule_total", "bidder_id"]).drop_duplicates(
        subset=["project_id", "bid_schedule_id"],
        keep="first",
    )

    if not low_totals.empty:
        low_totals = low_totals[["project_id", "bid_schedule_id", "bidder_id", "schedule_total"]].rename(
            columns={"bidder_id": "apparent_low_bidder_id_derived", "schedule_total": "apparent_low_total_derived"}
        )
        low_totals["selection_quality_flag"] = "OK"
    else:
        low_totals = pd.DataFrame(
            columns=[
                "project_id",
                "bid_schedule_id",
                "apparent_low_bidder_id_derived",
                "apparent_low_total_derived",
                "selection_quality_flag",
            ]
        )

    metrics = metric_core.merge(low_totals, on=["project_id", "bid_schedule_id"], how="left")
    metrics["selection_quality_flag"] = metrics["selection_quality_flag"].fillna("MISSING_TOTALS")

    out_cols = [
        "project_id",
        "bid_schedule_id",
        "pay_item_id",
        "avg_unit_price_3low",
        "median_unit_price",
        "min_unit_price",
        "num_bidders_valid",
        "apparent_low_total_derived",
        "apparent_low_bidder_id_derived",
        "selection_quality_flag",
    ]
    metrics[out_cols].to_csv(output_dir / "fact_project_pay_item_metrics.csv", index=False)


if __name__ == "__main__":
    main()
