#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.keys import stable_hash_int
from bidtabs.schemas import SOURCE_SYSTEM


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, keep_default_na=False)


def _to_numeric(df: pd.DataFrame, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _bool_mask(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def build_dim_project(df: pd.DataFrame, location_dict: pd.DataFrame) -> pd.DataFrame:
    loc_map = {}
    if not location_dict.empty and {"location_name_raw", "location_code"}.issubset(location_dict.columns):
        loc_map = {
            str(k).strip().upper(): str(v).strip()
            for k, v in zip(location_dict["location_name_raw"], location_dict["location_code"])
        }

    cols = ["project_ean", "solicitation_no", "project_name_raw", "letting_date", "location_name_raw", "source_file"]
    d = df[cols].drop_duplicates().copy()
    d["location_code"] = d["location_name_raw"].astype(str).str.upper().map(loc_map).fillna("")
    d["source_system"] = SOURCE_SYSTEM
    d["project_id"] = d.apply(
        lambda r: stable_hash_int([r["project_ean"], r["solicitation_no"], r["letting_date"], r["project_name_raw"], r["source_file"]]),
        axis=1,
    )
    d = d.rename(columns={"project_ean": "ean", "project_name_raw": "project_name"})
    return d[["project_id", "ean", "solicitation_no", "project_name", "letting_date", "location_name_raw", "location_code", "source_file", "source_system"]].sort_values("project_id")


def build_dim_bid_schedule(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["source_file", "bid_schedule_name", "bid_schedule_type", "bid_schedule_code"]
    d = df[cols].drop_duplicates().copy()
    d["bid_schedule_id"] = d.apply(
        lambda r: stable_hash_int([r["source_file"], r["bid_schedule_name"], r["bid_schedule_type"], r["bid_schedule_code"]]), axis=1
    )
    d = d.rename(columns={"bid_schedule_name": "schedule_name", "bid_schedule_type": "schedule_type", "bid_schedule_code": "schedule_code"})
    return d[["bid_schedule_id", "schedule_name", "schedule_type", "schedule_code", "source_file"]].sort_values("bid_schedule_id")


def build_dim_bidder(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["bidder_type", "bidder_name_raw", "bidder_name_canonical"]].drop_duplicates().copy()
    d["bidder_id"] = d.apply(lambda r: stable_hash_int([r["bidder_type"], r["bidder_name_canonical"]]), axis=1)
    d["contractor_name_canonical"] = d.apply(lambda r: r["bidder_name_canonical"] if r["bidder_type"] == "CONTRACTOR" else "", axis=1)
    return d[["bidder_id", "bidder_type", "bidder_name_raw", "bidder_name_canonical", "contractor_name_canonical"]].sort_values("bidder_id")


def build_dim_pay_item(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["item_code_raw", "item_code_norm", "section_code_raw", "section_code_norm", "item_description_clean"]
    d = df[cols].drop_duplicates().copy()
    d["pay_item_id"] = d.apply(lambda r: stable_hash_int([r["item_code_norm"], r["section_code_norm"], r["item_description_clean"]]), axis=1)
    d = d.rename(columns={"item_description_clean": "item_desc_canonical"})
    return d[["pay_item_id", "item_code_raw", "item_code_norm", "section_code_raw", "section_code_norm", "item_desc_canonical"]].sort_values("pay_item_id")


def build_dim_unit(df: pd.DataFrame) -> pd.DataFrame:
    d = df[["unit_code_norm"]].drop_duplicates().copy()
    d = d[d["unit_code_norm"].astype(str).str.strip() != ""]
    d["unit_group"] = ""
    d = d.rename(columns={"unit_code_norm": "unit_code"})
    return d[["unit_code", "unit_group"]].sort_values("unit_code")


def build_dim_specification(spec_mapping: pd.DataFrame, dim_pay_item: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if not spec_mapping.empty:
        expected = ["spec_section_code", "spec_section_name", "spec_division_code", "spec_division_name"]
        for col in expected:
            if col not in spec_mapping.columns:
                spec_mapping[col] = ""
        rows.append(spec_mapping[expected].drop_duplicates())

    inferred = dim_pay_item[["section_code_norm"]].drop_duplicates().rename(columns={"section_code_norm": "spec_section_code"})
    inferred = inferred[inferred["spec_section_code"].astype(str).str.strip() != ""]
    if not inferred.empty:
        inferred["spec_section_name"] = ""
        inferred["spec_division_code"] = ""
        inferred["spec_division_name"] = ""
        rows.append(inferred)

    if rows:
        d = pd.concat(rows, ignore_index=True).drop_duplicates()
    else:
        d = pd.DataFrame(columns=["spec_section_code", "spec_section_name", "spec_division_code", "spec_division_name"])
    d["spec_id"] = d["spec_section_code"].apply(lambda x: stable_hash_int(["spec", x]))
    return d[["spec_id", "spec_section_code", "spec_section_name", "spec_division_code", "spec_division_name"]].sort_values("spec_id")


def build_bridge_pay_item_spec(dim_pay_item: pd.DataFrame, dim_spec: pd.DataFrame) -> pd.DataFrame:
    spec_by_section = {str(s): sid for s, sid in zip(dim_spec["spec_section_code"], dim_spec["spec_id"]) if str(s).strip()}
    rows = []
    for _, r in dim_pay_item.iterrows():
        section = str(r.get("section_code_norm", "")).strip()
        if section and section in spec_by_section:
            rows.append(
                {
                    "pay_item_id": r["pay_item_id"],
                    "spec_id": spec_by_section[section],
                    "mapping_method": "DIRECT_SECTION",
                    "confidence": 1.0,
                    "is_curated": False,
                    "curated_by": "",
                    "curated_on": "",
                }
            )
    return pd.DataFrame(rows, columns=["pay_item_id", "spec_id", "mapping_method", "confidence", "is_curated", "curated_by", "curated_on"])


def build_analysis_tables(df: pd.DataFrame, location_dict: pd.DataFrame) -> dict:
    _to_numeric(df, ["quantity", "unit_price", "total_price", "total_price_calc", "schedule_total"])
    is_totals = _bool_mask(df["is_totals_row"])
    line_df = df[~is_totals].copy()
    totals_df = df[is_totals].copy()

    dim_project = build_dim_project(df, location_dict)
    dim_bid_schedule = build_dim_bid_schedule(df)
    dim_bidder = build_dim_bidder(df)
    dim_pay_item = build_dim_pay_item(line_df if not line_df.empty else df)
    dim_unit = build_dim_unit(line_df if not line_df.empty else df)

    project_key = dim_project[["project_id", "ean", "solicitation_no", "project_name", "letting_date", "source_file"]].drop_duplicates(
        subset=["ean", "solicitation_no", "project_name", "letting_date", "source_file"]
    )
    schedule_key = dim_bid_schedule[["bid_schedule_id", "schedule_name", "schedule_type", "schedule_code", "source_file"]].drop_duplicates(
        subset=["schedule_name", "schedule_type", "schedule_code", "source_file"]
    )
    bidder_key = dim_bidder[["bidder_id", "bidder_type", "bidder_name_canonical"]].drop_duplicates(subset=["bidder_type", "bidder_name_canonical"])
    pay_item_key = dim_pay_item[["pay_item_id", "item_code_norm", "section_code_norm", "item_desc_canonical"]].drop_duplicates(
        subset=["item_code_norm", "section_code_norm", "item_desc_canonical"]
    )

    fact_lines = (
        line_df.merge(
            project_key,
            left_on=["project_ean", "solicitation_no", "project_name_raw", "letting_date", "source_file"],
            right_on=["ean", "solicitation_no", "project_name", "letting_date", "source_file"],
            how="left",
        )
        .merge(
            schedule_key,
            left_on=["bid_schedule_name", "bid_schedule_type", "bid_schedule_code", "source_file"],
            right_on=["schedule_name", "schedule_type", "schedule_code", "source_file"],
            how="left",
        )
        .merge(
            bidder_key,
            on=["bidder_type", "bidder_name_canonical"],
            how="left",
        )
        .merge(
            pay_item_key,
            left_on=["item_code_norm", "section_code_norm", "item_description_clean"],
            right_on=["item_code_norm", "section_code_norm", "item_desc_canonical"],
            how="left",
        )
    )

    fact_bid_item_price = fact_lines[
        [
            "project_id",
            "bid_schedule_id",
            "pay_item_id",
            "bidder_id",
            "line_no",
            "quantity",
            "unit_code_norm",
            "unit_price",
            "total_price",
            "total_price_calc",
            "source_sheet",
            "source_row_index",
            "parse_confidence",
        ]
    ].rename(columns={"unit_code_norm": "unit_code", "source_row_index": "row_index"})

    if len(fact_bid_item_price) != len(line_df):
        raise ValueError(f"Join expansion detected: fact_bid_item_price rows={len(fact_bid_item_price)} line_rows={len(line_df)}")

    fact_totals = (
        totals_df.merge(
            project_key,
            left_on=["project_ean", "solicitation_no", "project_name_raw", "letting_date", "source_file"],
            right_on=["ean", "solicitation_no", "project_name", "letting_date", "source_file"],
            how="left",
        )
        .merge(
            schedule_key,
            left_on=["bid_schedule_name", "bid_schedule_type", "bid_schedule_code", "source_file"],
            right_on=["schedule_name", "schedule_type", "schedule_code", "source_file"],
            how="left",
        )
        .merge(
            bidder_key,
            on=["bidder_type", "bidder_name_canonical"],
            how="left",
        )
    )

    fact_bid_schedule_total = fact_totals[["project_id", "bid_schedule_id", "bidder_id", "schedule_total", "totals_row_label"]].rename(
        columns={"totals_row_label": "total_row_label"}
    )

    return {
        "line_df": line_df,
        "dim_project": dim_project,
        "dim_bid_schedule": dim_bid_schedule,
        "dim_bidder": dim_bidder,
        "dim_pay_item": dim_pay_item,
        "dim_unit": dim_unit,
        "fact_bid_item_price": fact_bid_item_price,
        "fact_bid_schedule_total": fact_bid_schedule_total,
    }


def main():
    parser = argparse.ArgumentParser(description="Build analysis schema tables from compiled_excel_itemized_clean.csv")
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--config_dir", default="./config")
    parser.add_argument("--emit_spec_tables", action="store_true", help="Emit optional spec mapping tables.")
    parser.add_argument("--emit_metrics", action="store_true", help="Reserved flag; metrics are built via scripts/build_metrics.py.")
    parser.add_argument("--emit_award_table", action="store_true", help="Emit optional empty fact_award table for extension workflows.")
    args = parser.parse_args()

    in_csv = Path(args.input_csv)
    out_dir = Path(args.output_dir)
    cfg = Path(args.config_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _read_csv(in_csv)
    if df.empty:
        raise SystemExit(f"No rows found in {in_csv}")

    location_dict = _read_csv(cfg / "location_dictionary.csv")
    spec_mapping = _read_csv(cfg / "spec_mapping.csv")
    tables = build_analysis_tables(df, location_dict)

    tables["dim_project"].to_csv(out_dir / "dim_project.csv", index=False)
    tables["dim_bid_schedule"].drop(columns=["source_file"], errors="ignore").to_csv(out_dir / "dim_bid_schedule.csv", index=False)
    tables["dim_bidder"].to_csv(out_dir / "dim_bidder.csv", index=False)
    tables["dim_pay_item"].to_csv(out_dir / "dim_pay_item.csv", index=False)
    tables["dim_unit"].to_csv(out_dir / "dim_unit.csv", index=False)
    tables["fact_bid_item_price"].to_csv(out_dir / "fact_bid_item_price.csv", index=False)
    tables["fact_bid_schedule_total"].to_csv(out_dir / "fact_bid_schedule_total.csv", index=False)

    if args.emit_spec_tables:
        dim_spec = build_dim_specification(spec_mapping, tables["dim_pay_item"])
        bridge = build_bridge_pay_item_spec(tables["dim_pay_item"], dim_spec)
        dim_spec.to_csv(out_dir / "dim_specification.csv", index=False)
        bridge.to_csv(out_dir / "bridge_pay_item_spec.csv", index=False)

    if args.emit_award_table:
        fact_award = pd.DataFrame(columns=["project_id", "bid_schedule_id", "external_selected_bidder_id", "external_selected_amount", "selection_source_note"])
        fact_award.to_csv(out_dir / "fact_award.csv", index=False)


if __name__ == "__main__":
    main()
