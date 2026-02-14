#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd


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


def _derive_standard_code(item_code_norm: str, section_code_norm: str) -> str:
    item = str(item_code_norm or "").strip()
    section = str(section_code_norm or "").strip()
    return item if item else section


def _derive_standard_cat(code: str) -> str:
    c = str(code or "").strip().upper()
    if not c:
        return "UNKNOWN"
    if re.match(r"^[A-Z]-?\d+(?:\.\d+)?$", c):
        return "FAA"
    if re.match(r"^\d{4,6}$", c):
        return "PDX"
    return "UNKNOWN"


def _extract_alt_code(description: str):
    if not description:
        return "", ""
    desc = str(description)
    m = re.search(r"Sections?\s*\d{4,6}(?:\s*(?:and|&)\s*\d{4,6})*", desc, re.IGNORECASE)
    if m:
        codes = re.findall(r"\d{4,6}", m.group(0))
        if len(codes) >= 2:
            return codes[0], codes[1]
        if len(codes) == 1:
            return codes[0], ""
    m = re.search(r"Item\s*([A-Z]-?\d+(?:\.\d+)?)", desc, re.IGNORECASE)
    if m:
        return m.group(1).strip(), ""
    m = re.search(r"Section\s*(\d{4,6})", desc, re.IGNORECASE)
    if m:
        return m.group(1).strip(), ""
    return "", ""


def _extract_spec_from_desc(desc: str, item_code_norm: str, section_code_norm: str) -> str:
    direct = _derive_standard_code(item_code_norm, section_code_norm)
    if direct:
        return direct
    primary, _ = _extract_alt_code(desc)
    return str(primary or "").strip()


def _clean_item_desc(desc: str) -> str:
    s = _clean_ws(desc)
    # Remove trailing specification fragment like (Item P-620), (Section 012210), (Sections 012200 and 334100)
    s = re.sub(r"\s*\((?:Item|Section|Sections)\s*[^)]*\)\s*$", "", s, flags=re.IGNORECASE)
    return _clean_ws(s)


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


# Backward-compatible helper kept for tests and utilities.
def build_dim_pay_item(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["item_code_raw", "item_code_norm", "section_code_raw", "section_code_norm", "item_description_raw", "item_description_clean"]
    d = df[cols].drop_duplicates().copy()
    d["standard_code"] = d.apply(lambda r: _extract_spec_from_desc(r["item_description_raw"], r["item_code_norm"], r["section_code_norm"]), axis=1)
    d["standard_cat"] = d["standard_code"].apply(_derive_standard_cat)
    d[["standard_code", "alt_code"]] = d["item_description_raw"].apply(lambda s: _extract_alt_code(s)).apply(pd.Series)
    d["standard_cat"] = d["standard_code"].apply(_derive_standard_cat)
    d["spec_extract"] = d["standard_code"].fillna("").astype(str)
    d["item_desc_raw"] = d["item_description_raw"].fillna("")
    d["item_desc_canonical"] = d["item_description_clean"].fillna("").astype(str).str.replace('"', "", regex=False)
    d = d.sort_values(["spec_extract", "item_desc_canonical", "item_desc_raw"], kind="stable").reset_index(drop=True)
    d["pay_item_id"] = range(1001, 1001 + len(d))
    return d[["pay_item_id", "spec_extract", "standard_code", "standard_cat", "item_code_raw", "section_code_raw", "alt_code", "item_desc_raw", "item_desc_canonical"]]


def _build_projects(df: pd.DataFrame, location_dict: pd.DataFrame) -> pd.DataFrame:
    base = build_dim_project(df, location_dict).copy()
    base["Advertise Date"] = pd.to_datetime(base["letting_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    projects = base.rename(
        columns={
            "project_id": "Project_ID",
            "ean": "EAN",
            "project_name": "Project Name",
            "location_code": "Location",
            "solicitation_no": "Solicitation No",
            "source_file": "PDF Link",
        }
    )
    projects["Project Name"] = projects["Project Name"].map(_clean_ws)
    return projects[["Project_ID", "EAN", "Project Name", "Advertise Date", "Location", "Solicitation No", "PDF Link"]]


def _project_join_key(df: pd.DataFrame):
    return [
        "project_ean",
        "solicitation_no",
        "project_name_raw",
        "letting_date",
        "location_name_raw",
        "source_file",
    ]


def _build_items(df: pd.DataFrame, projects: pd.DataFrame) -> pd.DataFrame:
    line = df[~_bool_mask(df["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""]
    line["spec_extract"] = line.apply(
        lambda r: _extract_spec_from_desc(r.get("item_description_raw", ""), r.get("item_code_norm", ""), r.get("section_code_norm", "")), axis=1
    )
    line["item_desc_cleaned"] = line["item_description_raw"].map(_clean_item_desc)
    line["unit_norm"] = line.get("unit_code_norm", pd.Series("", index=line.index)).astype(str).str.upper().str.strip()
    raw_unit = line.get("unit_code_raw", pd.Series("", index=line.index)).astype(str).str.upper().str.strip()
    line.loc[line["unit_norm"] == "", "unit_norm"] = raw_unit

    # Join Project_ID from project natural key.
    p = projects.rename(
        columns={
            "Project_ID": "Project_ID",
            "EAN": "project_ean",
            "Project Name": "project_name_raw",
            "Advertise Date": "letting_date",
            "Location": "location_code",
            "Solicitation No": "solicitation_no",
            "PDF Link": "source_file",
        }
    )
    # Use build_dim_project logic source join columns to avoid relying on transformed project name.
    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["Project_ID"] = projects["Project_ID"].values

    line = line.merge(proj_lookup, on=_project_join_key(df), how="left")

    item_cols = [
        "Project_ID",
        "line_no",
        "spec_extract",
        "item_desc_cleaned",
        "quantity",
        "unit_norm",
    ]
    items = line[item_cols].drop_duplicates().copy()
    items = items.sort_values(["Project_ID", "line_no", "spec_extract", "item_desc_cleaned"], kind="stable").reset_index(drop=True)
    items["Item_ID"] = range(1, len(items) + 1)

    items = items.rename(
        columns={
            "line_no": "Item Sequence",
            "spec_extract": "Specification Code",
            "item_desc_cleaned": "Item Description",
            "quantity": "Estimated Quantity",
            "unit_norm": "Unit",
        }
    )
    return items[["Item_ID", "Project_ID", "Item Sequence", "Specification Code", "Item Description", "Estimated Quantity", "Unit"]]


def _build_bids(df: pd.DataFrame, projects: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    line = df[~_bool_mask(df["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""]

    line["spec_extract"] = line.apply(
        lambda r: _extract_spec_from_desc(r.get("item_description_raw", ""), r.get("item_code_norm", ""), r.get("section_code_norm", "")), axis=1
    )
    line["item_desc_cleaned"] = line["item_description_raw"].map(_clean_item_desc)

    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["Project_ID"] = projects["Project_ID"].values
    line = line.merge(proj_lookup, on=_project_join_key(df), how="left")

    item_lookup = items.rename(
        columns={
            "Item_ID": "Item_ID",
            "Item Sequence": "line_no",
            "Specification Code": "spec_extract",
            "Item Description": "item_desc_cleaned",
            "Estimated Quantity": "quantity",
            "Unit": "unit_norm",
        }
    )
    line = line.merge(item_lookup[["Item_ID", "Project_ID", "line_no", "spec_extract", "item_desc_cleaned"]], on=["Project_ID", "line_no", "spec_extract", "item_desc_cleaned"], how="left")

    line["is_ee"] = _is_engineers_estimate(line)
    line["Contractor Name"] = line.get("bidder_name_canonical", "").astype(str)
    line["Unit Price"] = pd.to_numeric(line.get("unit_price", None), errors="coerce")
    qty = pd.to_numeric(line.get("quantity", None), errors="coerce")
    total = pd.to_numeric(line.get("total_price", None), errors="coerce")
    line["Total Price"] = total
    line.loc[line["Total Price"].isna(), "Total Price"] = line["Unit Price"] * qty

    # Winner by project total (excluding Engineer's Estimate).
    contract_rows = line[~line["is_ee"]].copy()
    totals = (
        contract_rows.groupby(["Project_ID", "Contractor Name"], dropna=False)["Total Price"]
        .sum(min_count=1)
        .reset_index(name="project_total")
    )
    min_totals = totals.groupby("Project_ID", dropna=False)["project_total"].transform("min")
    totals["is_winner_contract"] = totals["project_total"].notna() & totals["project_total"].eq(min_totals)
    winner_map = totals[totals["is_winner_contract"]][["Project_ID", "Contractor Name"]].assign(Is_Winner=True)

    line = line.merge(winner_map, on=["Project_ID", "Contractor Name"], how="left")
    line["Is_Winner"] = line["Is_Winner"].astype(bool)
    line.loc[line["is_ee"], "Is_Winner"] = False

    # Rank per item by unit price (excluding Engineer's Estimate from ranking sequence).
    rank_df = line[~line["is_ee"] & line["Unit Price"].notna()].copy()
    rank_df["Rank"] = rank_df.groupby("Item_ID")["Unit Price"].rank(method="dense", ascending=True)
    line = line.merge(rank_df[["Item_ID", "Contractor Name", "Unit Price", "Rank"]], on=["Item_ID", "Contractor Name", "Unit Price"], how="left")

    bids = line[["Item_ID", "Contractor Name", "Unit Price", "Total Price", "Is_Winner", "Rank"]].copy()
    bids = bids.sort_values(["Item_ID", "Contractor Name", "Unit Price"], kind="stable").reset_index(drop=True)
    bids.insert(0, "Bid_ID", range(1, len(bids) + 1))

    # Integer rank for ranked rows, blank otherwise (EE / missing unit price).
    bids["Rank"] = bids["Rank"].apply(lambda x: "" if pd.isna(x) else int(x))
    return bids


def build_analysis_tables(df: pd.DataFrame, location_dict: pd.DataFrame) -> dict:
    _to_numeric(df, ["quantity", "unit_price", "total_price"])
    projects = _build_projects(df, location_dict)
    items = _build_items(df, projects)
    bids = _build_bids(df, projects, items)
    return {
        "Projects": projects,
        "Items": items,
        "Bids": bids,
    }


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
