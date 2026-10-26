#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd


def _norm_text(s: str) -> str:
    s = str(s or "").upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _spec_suffix(spec: str) -> str:
    spec = str(spec or "").strip().upper()
    if not spec or spec == "UNCLASSIFIED":
        return ""
    if re.match(r"^\d{6}$", spec):
        return f" (Section {spec})"
    return f" (Item {spec})"


def _canonicalized_items(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["base_desc"] = work["pay_item_description"].astype(str).str.strip()
    work.loc[work["base_desc"] == "", "base_desc"] = work["item_description_raw"].astype(str).str.strip()
    work["specification"] = work["specification"].astype(str).str.strip().str.upper()
    work["canon_key"] = work["specification"] + "|" + work["base_desc"].map(_norm_text)

    # Pick the most frequent readable description per canonical key.
    display = (
        work.groupby(["canon_key", "base_desc"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["canon_key", "n", "base_desc"], ascending=[True, False, True], kind="stable")
        .drop_duplicates(subset=["canon_key"], keep="first")[["canon_key", "base_desc"]]
        .rename(columns={"base_desc": "display_desc"})
    )

    work = work.merge(display, on="canon_key", how="left")
    work["item_label"] = work["display_desc"] + work["specification"].map(_spec_suffix)
    return work


def _pivot_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    grouped = (
        df.groupby(["item_group", "item_subgroup"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["n", "item_group", "item_subgroup"], ascending=[False, True, True], kind="stable")
    )

    for item_group in grouped["item_group"].drop_duplicates():
        gdf = df[df["item_group"] == item_group]
        group_n = len(gdf)
        rows.append({"Row Labels": item_group, "Count of item_description_raw": int(group_n)})

        subgroups = (
            gdf.groupby("item_subgroup", dropna=False)
            .size()
            .reset_index(name="n")
            .sort_values(["n", "item_subgroup"], ascending=[False, True], kind="stable")
        )
        for _, srow in subgroups.iterrows():
            subgroup = srow["item_subgroup"]
            sdf = gdf[gdf["item_subgroup"] == subgroup]
            rows.append({"Row Labels": subgroup, "Count of item_description_raw": int(len(sdf))})

            item_counts = (
                sdf.groupby("item_label", dropna=False)
                .size()
                .reset_index(name="n")
                .sort_values(["n", "item_label"], ascending=[False, True], kind="stable")
            )
            for _, irow in item_counts.iterrows():
                rows.append({"Row Labels": irow["item_label"], "Count of item_description_raw": int(irow["n"])})

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export pivot-style grouping rollup to XLSX.")
    parser.add_argument("--proposal_csv", default="./reports/item_grouping_proposal.csv")
    parser.add_argument("--out_xlsx", default="./reports/item_grouping_pivot.xlsx")
    parser.add_argument("--out_csv", default="./reports/item_grouping_pivot.csv")
    args = parser.parse_args()

    proposal = pd.read_csv(Path(args.proposal_csv), keep_default_na=False)
    canon = _canonicalized_items(proposal)
    pivot_df = _pivot_rows(canon)

    out_xlsx = Path(args.out_xlsx)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        pivot_df.to_excel(writer, index=False, sheet_name="Pivot")
        ws = writer.sheets["Pivot"]
        ws.freeze_panes(1, 0)
        ws.set_column("A:A", 110)
        ws.set_column("B:B", 28)

    pivot_df.to_csv(Path(args.out_csv), index=False)
    print(f"Wrote {out_xlsx} ({len(pivot_df)} rows)")
    print(f"Wrote {args.out_csv} ({len(pivot_df)} rows)")


if __name__ == "__main__":
    main()
