from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from .config import load_location_dictionary
from .parse_items import parse_item_fields


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, keep_default_na=False)


def _to_numeric(df: pd.DataFrame, cols) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _bool_mask(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


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
    return ["project_ean", "solicitation_no", "project_name_raw", "letting_date", "location_name_raw", "source_file"]


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
    d = d.rename(columns={"project_ean": "ean", "project_name_raw": "project_name", "source_file": "pdf_link"})
    d = d.sort_values(["ean", "solicitation_no", "pdf_link", "project_name"], kind="stable").reset_index(drop=True)
    d["project_id"] = range(1, len(d) + 1)
    d["advertise_date"] = pd.to_datetime(d["letting_date"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    d["location"] = d["location_code"]
    return d[["project_id", "ean", "project_name", "advertise_date", "location", "solicitation_no", "pdf_link"]]


def _parsed_item_fields(series: pd.Series) -> pd.DataFrame:
    parsed = series.astype(str).apply(parse_item_fields)
    out = pd.DataFrame(parsed.tolist(), index=series.index)
    out = out.rename(columns={
        "spec_code_primary": "specification",
        "spec_code_alternates": "alternate_specification",
        "item": "pay_item_description",
        "supplemental_description": "supplemental_description",
        "item_display": "item",
    })
    return out[["specification", "alternate_specification", "pay_item_description", "supplemental_description", "item", "parse_type", "desc_core"]]


def _ensure_parsed_columns(df: pd.DataFrame) -> pd.DataFrame:
    needed = ["specification", "alternate_specification", "pay_item_description", "supplemental_description", "item", "parse_type", "desc_core"]
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

    item_cols = ["project_id", "line_no", "item_description_raw", "specification", "alternate_specification", "pay_item_description", "supplemental_description", "item", "quantity", "unit_norm"]
    items = line[item_cols].drop_duplicates().copy()
    items = items.sort_values(["project_id", "line_no", "specification", "item", "item_description_raw"], kind="stable").reset_index(drop=True)
    items["item_id"] = range(1, len(items) + 1)

    return items[["item_id", "project_id", "line_no", "item_description_raw", "specification", "alternate_specification", "pay_item_description", "supplemental_description", "item", "quantity", "unit_norm"]]


def _build_bids(df: pd.DataFrame, projects: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    line = df[~_bool_mask(df["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""]
    line = _ensure_parsed_columns(line)

    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["project_id"] = projects["project_id"].values
    line = line.merge(proj_lookup, on=_project_join_key(df), how="left")

    item_lookup = items.rename(columns={
        "item_description_raw": "item_description_raw_join",
        "specification": "specification_join",
        "alternate_specification": "alternate_specification_join",
        "pay_item_description": "pay_item_description_join",
        "supplemental_description": "supplemental_description_join",
        "item": "item_join",
    })
    line["item_description_raw_join"] = line.get("item_description_raw", "").astype(str)
    line["specification_join"] = line["specification"]
    line["alternate_specification_join"] = line["alternate_specification"]
    line["pay_item_description_join"] = line["pay_item_description"]
    line["supplemental_description_join"] = line["supplemental_description"]
    line["item_join"] = line["item"]

    line = line.merge(
        item_lookup[["item_id", "project_id", "line_no", "item_description_raw_join", "specification_join", "alternate_specification_join", "pay_item_description_join", "supplemental_description_join", "item_join"]],
        left_on=["project_id", "line_no", "item_description_raw_join", "specification_join", "alternate_specification_join", "pay_item_description_join", "supplemental_description_join", "item_join"],
        right_on=["project_id", "line_no", "item_description_raw_join", "specification_join", "alternate_specification_join", "pay_item_description_join", "supplemental_description_join", "item_join"],
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
    totals = contract_rows.groupby(["project_id", "contractor_name"], dropna=False)["total_price"].sum(min_count=1).reset_index(name="project_total")
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


def _build_scope(df: pd.DataFrame, projects: pd.DataFrame) -> pd.DataFrame:
    cols = _project_join_key(df) + ["source_sheet", "bid_schedule_name", "bid_schedule_type", "bid_schedule_code"]
    d = df[cols].drop_duplicates().copy()
    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["project_id"] = projects["project_id"].values
    d = d.merge(proj_lookup, on=_project_join_key(df), how="left")
    d["scope_type"] = d["bid_schedule_type"].astype(str).str.upper().replace({"ALTERNATE": "ALT"})
    d.loc[~d["scope_type"].isin(["BASE", "ALT"]), "scope_type"] = "BASE"
    d["scope_code"] = d["bid_schedule_code"].astype(str).where(d["bid_schedule_code"].astype(str).str.strip() != "", d["source_sheet"].astype(str))
    d = d.sort_values(["project_id", "scope_type", "scope_code", "source_sheet"], kind="stable").reset_index(drop=True)
    d["scope_id"] = range(1, len(d) + 1)
    return d[["scope_id", "project_id", "source_sheet", "bid_schedule_name", "bid_schedule_type", "bid_schedule_code", "scope_type", "scope_code"]]


def _build_bidder(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["bidder_name_raw", "bidder_name_canonical", "bidder_type", "is_engineers_estimate"]
    d = df[cols].drop_duplicates().copy()
    d = d.sort_values(["bidder_type", "bidder_name_canonical", "bidder_name_raw"], kind="stable").reset_index(drop=True)
    d["bidder_id"] = range(1, len(d) + 1)
    return d[["bidder_id", "bidder_name_raw", "bidder_name_canonical", "bidder_type", "is_engineers_estimate"]]


def _build_fact(df: pd.DataFrame, projects: pd.DataFrame, scopes: pd.DataFrame, bidders: pd.DataFrame, pay_items: pd.DataFrame) -> pd.DataFrame:
    line = df[~_bool_mask(df["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""]
    line = _ensure_parsed_columns(line)
    line = _to_numeric(line, ["quantity", "unit_price", "total_price"])

    proj_lookup = df[_project_join_key(df)].drop_duplicates().copy()
    proj_lookup = proj_lookup.sort_values(_project_join_key(df), kind="stable").reset_index(drop=True)
    proj_lookup["project_id"] = projects["project_id"].values
    line = line.merge(proj_lookup, on=_project_join_key(df), how="left")

    scope_lookup = scopes[["scope_id", "project_id", "source_sheet", "bid_schedule_name", "bid_schedule_type", "bid_schedule_code"]].drop_duplicates()
    line = line.merge(scope_lookup, on=["project_id", "source_sheet", "bid_schedule_name", "bid_schedule_type", "bid_schedule_code"], how="left")

    bidder_lookup = bidders[["bidder_id", "bidder_name_raw", "bidder_name_canonical", "bidder_type", "is_engineers_estimate"]].drop_duplicates()
    line = line.merge(bidder_lookup, on=["bidder_name_raw", "bidder_name_canonical", "bidder_type", "is_engineers_estimate"], how="left")

    pay_lookup = pay_items.rename(columns={
        "spec_extract": "specification_join",
        "alt_code": "alternate_specification_join",
        "item_desc_raw": "item_description_raw_join",
        "item_desc_canonical": "item_description_clean_join",
    })
    line["specification_join"] = line["specification"]
    line["alternate_specification_join"] = line["alternate_specification"]
    line["item_description_raw_join"] = line["item_description_raw"].astype(str)
    line["item_description_clean_join"] = line["item_description_clean"].astype(str).str.replace('"', "", regex=False)
    line = line.merge(
        pay_lookup[["pay_item_id", "specification_join", "alternate_specification_join", "item_description_raw_join", "item_description_clean_join"]],
        on=["specification_join", "alternate_specification_join", "item_description_raw_join", "item_description_clean_join"],
        how="left",
    )

    contract_rows = line[~_is_engineers_estimate(line)].copy()
    totals = contract_rows.groupby(["project_id", "bidder_name_canonical"], dropna=False)["total_price"].sum(min_count=1).reset_index(name="project_total")
    min_totals = totals.groupby("project_id", dropna=False)["project_total"].transform("min")
    totals["is_winner"] = totals["project_total"].notna() & totals["project_total"].eq(min_totals)
    line = line.merge(totals[["project_id", "bidder_name_canonical", "is_winner"]], on=["project_id", "bidder_name_canonical"], how="left")
    line["is_winner"] = line["is_winner"].fillna(False).astype(bool)
    line.loc[_is_engineers_estimate(line), "is_winner"] = False

    rank_df = line[~_is_engineers_estimate(line) & line["unit_price"].notna()].copy()
    rank_df["rank"] = rank_df.groupby(["project_id", "scope_id", "pay_item_id"])["unit_price"].rank(method="dense", ascending=True)
    line = line.merge(rank_df[["project_id", "scope_id", "pay_item_id", "bidder_name_canonical", "unit_price", "rank"]], on=["project_id", "scope_id", "pay_item_id", "bidder_name_canonical", "unit_price"], how="left")
    line["rank"] = line["rank"].apply(lambda x: "" if pd.isna(x) else int(x))

    scope_type = line.get("bid_schedule_type", pd.Series("", index=line.index)).astype(str).str.upper().replace({"ALTERNATE": "ALT"})
    line["scope_type"] = scope_type.where(scope_type.isin(["BASE", "ALT"]), "BASE")
    line["scope_code"] = line.get("bid_schedule_code", pd.Series("", index=line.index)).astype(str)

    cols = [
        "project_id", "scope_id", "bidder_id", "pay_item_id",
        "extract_run_id", "source_file", "source_sheet", "source_row_index", "parse_confidence",
        "project_ean", "solicitation_no", "project_name_raw", "letting_date", "location_name_raw",
        "scope_type", "scope_code", "bid_schedule_name", "bid_schedule_type", "bid_schedule_code",
        "line_no", "specification", "alternate_specification", "pay_item_description", "supplemental_description", "item", "quantity", "unit_code_norm",
        "bidder_name_canonical", "bidder_type", "is_engineers_estimate",
        "unit_price", "total_price", "price_valid_flag", "is_winner", "rank",
    ]
    for col in cols:
        if col not in line.columns:
            line[col] = ""
    fact = line[cols].sort_values(["project_id", "scope_id", "pay_item_id", "bidder_id", "source_row_index"], kind="stable").reset_index(drop=True)
    return fact


def build_analysis_tables(df: pd.DataFrame, location_dict: pd.DataFrame) -> dict:
    _to_numeric(df, ["quantity", "unit_price", "total_price"])
    projects = _build_projects(df, location_dict)
    items = _build_items(df, projects)
    bids = _build_bids(df, projects, items)
    return {"Projects": projects, "Items": items, "Bids": bids}


def build_model(clean_df: pd.DataFrame, config_tables: dict | str | Path) -> dict[str, pd.DataFrame | dict[str, pd.DataFrame]]:
    df = clean_df.copy()
    _to_numeric(df, ["quantity", "unit_price", "total_price"])
    location_dict = load_location_dictionary(config_tables) if isinstance(config_tables, (str, Path)) else config_tables.get("location_dictionary", pd.DataFrame())

    dim_project = build_dim_project(df, location_dict)
    dim_scope = _build_scope(df, dim_project.rename(columns={"ean": "project_ean", "project_name": "project_name_raw", "source_file": "source_file"}))
    dim_bidder = _build_bidder(df)
    dim_pay_item = build_dim_pay_item(df)
    fact = _build_fact(df, dim_project, dim_scope, dim_bidder, dim_pay_item)
    compat = build_analysis_tables(df, location_dict)

    return {
        "fact": fact,
        "dim_project": dim_project,
        "dim_scope": dim_scope,
        "dim_bidder": dim_bidder,
        "dim_pay_item": dim_pay_item,
        "compat": compat,
    }


def write_model_outputs(clean_csv: Path | str, out_dir: Path | str, config_dir: Path | str = "./config") -> dict[str, pd.DataFrame | dict[str, pd.DataFrame]]:
    clean_csv = Path(clean_csv)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = _read_csv(clean_csv)
    if df.empty:
        raise SystemExit(f"No rows found in {clean_csv}")

    model = build_model(df, config_dir)
    model["fact"].to_csv(out_dir / "fact_bid_item_enriched.csv", index=False)
    model["dim_project"].to_csv(out_dir / "dim_project.csv", index=False)
    model["dim_scope"].to_csv(out_dir / "dim_scope.csv", index=False)
    model["dim_bidder"].to_csv(out_dir / "dim_bidder.csv", index=False)
    model["dim_pay_item"].to_csv(out_dir / "dim_pay_item.csv", index=False)

    compat = model["compat"]
    compat["Projects"].to_csv(out_dir / "Projects.csv", index=False)
    compat["Items"].to_csv(out_dir / "Items.csv", index=False)
    compat["Bids"].to_csv(out_dir / "Bids.csv", index=False)
    return model
