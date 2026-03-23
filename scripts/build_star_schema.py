#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from bidtabs.parse_items import parse_item_fields


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


def _clean_ws(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_location_key(value: str) -> str:
    s = str(value or "").upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def _derive_standard_cat(code: str) -> str:
    c = str(code or "").strip().upper()
    if not c or c == "UNCLASSIFIED":
        return "UNKNOWN"
    if re.match(r"^[A-Z]{1,2}-\d{3}$", c):
        return "FAA"
    if re.match(r"^\d{4,6}$", c):
        return "PDX"
    return "UNKNOWN"


def _is_engineers_estimate(df: pd.DataFrame) -> pd.Series:
    bidder_type = df.get("bidder_type", pd.Series("", index=df.index)).astype(str).str.upper()
    bidder_name = df.get("bidder_name_canonical", pd.Series("", index=df.index)).astype(str).str.upper()
    return bidder_type.eq("ENGINEERS_ESTIMATE") | bidder_name.str.contains("ENGINEER", na=False)




# Backward-compatible helper kept for tests and utilities.
def build_dim_project(df: pd.DataFrame, location_dict: pd.DataFrame) -> pd.DataFrame:
    loc_map = {}
    if not location_dict.empty and {"location_name_raw", "location_code"}.issubset(location_dict.columns):
        loc_map = {
            _normalize_location_key(k): str(v).strip().upper()
            for k, v in zip(location_dict["location_name_raw"], location_dict["location_code"])
        }

    cols = ["project_ean", "solicitation_no", "project_name_raw", "letting_date", "location_name_raw", "source_file"]
    d = df[cols].drop_duplicates().copy()
    d["location_code"] = d["location_name_raw"].astype(str).map(_normalize_location_key).map(loc_map).fillna("")
    d = d.rename(columns={"project_ean": "ean", "project_name_raw": "project_name"})
    d = d.sort_values(["ean", "solicitation_no", "source_file", "project_name"], kind="stable").reset_index(drop=True)
    d["project_id"] = range(1, len(d) + 1)
    d["source_system"] = "excel_bidtab"
    return d[["project_id", "ean", "solicitation_no", "project_name", "letting_date", "location_name_raw", "location_code", "source_file", "source_system"]]


def _extract_alt_code(description: str):
    fields = parse_item_fields(description)
    if fields["parse_type"] in {"ITEM", "SECTION"}:
        return fields["spec_code_primary"], fields["spec_code_alternates"]
    return "", ""


def build_dim_pay_item(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["item_code_raw", "item_code_norm", "section_code_raw", "section_code_norm", "item_description_raw", "item_description_clean"]
    d = df[cols].drop_duplicates().copy()
    parsed = d["item_description_raw"].astype(str).apply(parse_item_fields)
    p = pd.DataFrame(parsed.tolist(), index=d.index)

    d["spec_extract"] = p["spec_code_primary"].fillna("")
    d["standard_code"] = d["spec_extract"]
    d["standard_cat"] = d["standard_code"].apply(_derive_standard_cat)
    d["alt_code"] = p["spec_code_alternates"].fillna("")
    d["item_desc_raw"] = d["item_description_raw"].fillna("")
    d["item_desc_canonical"] = p["desc_core"].fillna("").astype(str).str.replace('"', "", regex=False)
    d = d.sort_values(["spec_extract", "item_desc_canonical", "item_desc_raw"], kind="stable").reset_index(drop=True)
    d["pay_item_id"] = range(1001, 1001 + len(d))
    return d[["pay_item_id", "spec_extract", "standard_code", "standard_cat", "item_code_raw", "section_code_raw", "alt_code", "item_desc_raw", "item_desc_canonical"]]


def _project_join_key(df: pd.DataFrame):
    return [
        "project_ean",
        "solicitation_no",
        "project_name_raw",
        "letting_date",
        "location_name_raw",
        "source_file",
    ]


def _build_projects(df: pd.DataFrame, location_dict: pd.DataFrame) -> pd.DataFrame:
    loc_map = {}
    if not location_dict.empty and {"location_name_raw", "location_code"}.issubset(location_dict.columns):
        loc_map = {
            _normalize_location_key(k): str(v).strip().upper()
            for k, v in zip(location_dict["location_name_raw"], location_dict["location_code"])
        }

    cols = ["project_ean", "solicitation_no", "project_name_raw", "letting_date", "location_name_raw", "source_file"]
    d = df[cols].drop_duplicates().copy()
    d["location_code"] = d["location_name_raw"].astype(str).map(_normalize_location_key).map(loc_map).fillna("")
    d = d.rename(columns={"project_ean": "ean", "project_name_raw": "project_name", "solicitation_no": "solicitation_no", "source_file": "pdf_link"})
    d = d.sort_values(["ean", "solicitation_no", "pdf_link", "project_name"], kind="stable").reset_index(drop=True)
    d["project_id"] = range(1, len(d) + 1)
    d["advertise_date"] = pd.to_datetime(d["letting_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    d["location"] = d["location_code"]
    return d[["project_id", "ean", "project_name", "advertise_date", "location", "solicitation_no", "pdf_link"]]


def _parsed_item_fields(series: pd.Series) -> pd.DataFrame:
    parsed = series.astype(str).apply(parse_item_fields)
    out = pd.DataFrame(parsed.tolist(), index=series.index)
    out = out.rename(
        columns={
            "spec_code_primary": "specification",
            "spec_code_alternates": "alternate_specification",
            "item": "pay_item_description",
            "supplemental_description": "supplemental_description",
            "item_display": "item",
        }
    )
    return out[["specification", "alternate_specification", "pay_item_description", "supplemental_description", "item", "parse_type", "desc_core"]]




def _ensure_parsed_columns(df: pd.DataFrame) -> pd.DataFrame:
    needed = [
        "specification",
        "alternate_specification",
        "pay_item_description",
        "supplemental_description",
        "item",
        "parse_type",
        "desc_core",
    ]
    missing = [c for c in needed if c not in df.columns]
    if not missing:
        return df

    parsed = _parsed_item_fields(df.get("item_description_raw", pd.Series("", index=df.index)))
    out = df.copy()
    for c in missing:
        out[c] = parsed[c]
    return out

def _build_items(df: pd.DataFrame, projects: pd.DataFrame) -> pd.DataFrame:
    line = df[~_bool_mask(df["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""]

    line = _ensure_parsed_columns(line)

    line["unit_norm"] = line.get("unit_code_norm", pd.Series("", index=line.index)).astype(str).str.upper().str.strip()
    raw_unit = line.get("unit_code_raw", pd.Series("", index=line.index)).astype(str).str.upper().str.strip()
    line.loc[line["unit_norm"] == "", "unit_norm"] = raw_unit

    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["project_id"] = projects["project_id"].values
    line = line.merge(proj_lookup, on=_project_join_key(df), how="left")

    line["item_description_raw"] = line.get("item_description_raw", "").astype(str)

    item_cols = [
        "project_id",
        "line_no",
        "item_description_raw",
        "specification",
        "alternate_specification",
        "pay_item_description",
        "supplemental_description",
        "item",
        "quantity",
        "unit_norm",
    ]
    items = line[item_cols].drop_duplicates().copy()
    items = items.sort_values(["project_id", "line_no", "specification", "item", "item_description_raw"], kind="stable").reset_index(drop=True)
    items["item_id"] = range(1, len(items) + 1)

    return items[
        [
            "item_id",
            "project_id",
            "line_no",
            "item_description_raw",
            "specification",
            "alternate_specification",
            "pay_item_description",
            "supplemental_description",
            "item",
            "quantity",
            "unit_norm",
        ]
    ]


def _build_bids(df: pd.DataFrame, projects: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    line = df[~_bool_mask(df["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""]

    line = _ensure_parsed_columns(line)

    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["project_id"] = projects["project_id"].values
    line = line.merge(proj_lookup, on=_project_join_key(df), how="left")

    item_lookup = items.rename(
        columns={
            "item_description_raw": "item_description_raw_join",
            "specification": "specification_join",
            "alternate_specification": "alternate_specification_join",
            "pay_item_description": "pay_item_description_join",
            "supplemental_description": "supplemental_description_join",
            "item": "item_join",
        }
    )
    line["item_description_raw_join"] = line.get("item_description_raw", "").astype(str)
    line["specification_join"] = line["specification"]
    line["alternate_specification_join"] = line["alternate_specification"]
    line["pay_item_description_join"] = line["pay_item_description"]
    line["supplemental_description_join"] = line["supplemental_description"]
    line["item_join"] = line["item"]

    line = line.merge(
        item_lookup[
            [
                "item_id",
                "project_id",
                "line_no",
                "item_description_raw_join",
                "specification_join",
                "alternate_specification_join",
                "pay_item_description_join",
                "supplemental_description_join",
                "item_join",
            ]
        ],
        left_on=[
            "project_id",
            "line_no",
            "item_description_raw_join",
            "specification_join",
            "alternate_specification_join",
            "pay_item_description_join",
            "supplemental_description_join",
            "item_join",
        ],
        right_on=[
            "project_id",
            "line_no",
            "item_description_raw_join",
            "specification_join",
            "alternate_specification_join",
            "pay_item_description_join",
            "supplemental_description_join",
            "item_join",
        ],
        how="left",
    )

    line["is_ee"] = _is_engineers_estimate(line)
    line["contractor_name"] = line.get("bidder_name_canonical", "").astype(str)
    line["unit_price"] = pd.to_numeric(line.get("unit_price", None), errors="coerce")
    qty = pd.to_numeric(line.get("quantity", None), errors="coerce")
    total = pd.to_numeric(line.get("total_price", None), errors="coerce")
    line["total_price"] = total
    line.loc[line["total_price"].isna(), "total_price"] = line["unit_price"] * qty

    contract_rows = line[~line["is_ee"]].copy()
    totals = (
        contract_rows.groupby(["project_id", "contractor_name"], dropna=False)["total_price"]
        .sum(min_count=1)
        .reset_index(name="project_total")
    )
    min_totals = totals.groupby("project_id", dropna=False)["project_total"].transform("min")
    totals["is_winner_contract"] = totals["project_total"].notna() & totals["project_total"].eq(min_totals)
    winner_map = totals[totals["is_winner_contract"]][["project_id", "contractor_name"]].assign(is_winner=True)

    line = line.merge(winner_map, on=["project_id", "contractor_name"], how="left")
    line["is_winner"] = line["is_winner"].astype(bool)
    line.loc[line["is_ee"], "is_winner"] = False

    rank_df = line[~line["is_ee"] & line["unit_price"].notna()].copy()
    rank_df["rank"] = rank_df.groupby("item_id")["unit_price"].rank(method="dense", ascending=True)
    line = line.merge(rank_df[["item_id", "contractor_name", "unit_price", "rank"]], on=["item_id", "contractor_name", "unit_price"], how="left")

    bids = line[["item_id", "contractor_name", "unit_price", "total_price", "is_winner", "rank"]].copy()
    bids = bids.sort_values(["item_id", "contractor_name", "unit_price"], kind="stable").reset_index(drop=True)
    bids.insert(0, "bid_id", range(1, len(bids) + 1))
    bids["rank"] = bids["rank"].apply(lambda x: "" if pd.isna(x) else int(x))
    return bids


def build_analysis_tables(df: pd.DataFrame, location_dict: pd.DataFrame) -> dict:
    _to_numeric(df, ["quantity", "unit_price", "total_price"])
    projects = _build_projects(df, location_dict)
    items = _build_items(df, projects)
    bids = _build_bids(df, projects, items)
    return {"Projects": projects, "Items": items, "Bids": bids}


def main():
    parser = argparse.ArgumentParser(description="Build 3-table analytical star schema (Projects, Items, Bids) from compiled extract")
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--config_dir", default="./config")
    args = parser.parse_args()

    in_csv = Path(args.input_csv)
    out_dir = Path(args.output_dir)
    cfg = Path(args.config_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    df = _read_csv(in_csv)
    if df.empty:
        raise SystemExit(f"No rows found in {in_csv}")

    location_dict = _read_csv(cfg / "location_dictionary.csv")
    tables = build_analysis_tables(df, location_dict)

    tables["Projects"].to_csv(out_dir / "Projects.csv", index=False)
    tables["Items"].to_csv(out_dir / "Items.csv", index=False)
    tables["Bids"].to_csv(out_dir / "Bids.csv", index=False)

    print(f"Wrote {out_dir / 'Projects.csv'} ({len(tables['Projects'])} rows)")
    print(f"Wrote {out_dir / 'Items.csv'} ({len(tables['Items'])} rows)")
    print(f"Wrote {out_dir / 'Bids.csv'} ({len(tables['Bids'])} rows)")


if __name__ == "__main__":
    main()
