#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.io_excel import load_workbook_data
from bidtabs.normalize import canonicalize_name, clean_whitespace, load_name_map
from bidtabs.parse_header import parse_project_header
from bidtabs.parse_items import iter_item_rows
from bidtabs.parse_table import detect_schedule_fields, parse_table_structure
from bidtabs.qa import ParseIssue, enforce_canonical_key_uniqueness, write_parse_summary, write_qa_reports
from bidtabs.schemas import SCHEMA_VERSION, coerce_compiled_record, compiled_columns


def classify_bidder(name: str):
    lower = clean_whitespace(name).lower()
    is_est = "engineer" in lower and "estimate" in lower
    bidder_type = "ENGINEERS_ESTIMATE" if is_est else "CONTRACTOR"
    return bidder_type, is_est


def detect_candidate_sheet(ws) -> bool:
    item_rows = 0
    for r in range(1, ws.max_row + 1):
        row_vals = [clean_whitespace(ws.cell(row=r, column=c).value).lower() for c in range(1, ws.max_column + 1)]
        if "item no." in row_vals or "item no" in row_vals:
            unit_count = row_vals.count("unit price")
            total_count = row_vals.count("total price")
            if unit_count >= 2 and total_count >= 2:
                item_rows += 1
    return item_rows >= 1


def extract_file(path: Path, run_id: str, name_map: Dict[str, str], parse_issues: List[ParseIssue]) -> List[dict]:
    records: List[dict] = []
    wb = load_workbook_data(path)
    for ws in wb.worksheets:
        if not detect_candidate_sheet(ws):
            continue

        structure = parse_table_structure(ws)
        if structure.table_header_row < 0:
            parse_issues.append(ParseIssue(path.name, ws.title, "header_detection", ";".join(structure.warnings)))
            continue
        if structure.warnings:
            parse_issues.append(ParseIssue(path.name, ws.title, "parse_warning", ";".join(structure.warnings)))
        if not structure.bidder_blocks:
            continue

        header = parse_project_header(ws, structure.table_header_row)
        schedule = detect_schedule_fields(ws.title)

        for item in iter_item_rows(ws, structure.table_header_row, structure.col_map, structure.bidder_blocks):
            bidder_raw = item["bidder_name_raw"]
            bidder_canon = canonicalize_name(bidder_raw, name_map)
            bidder_type, is_est = classify_bidder(bidder_raw)
            parse_confidence = 0.95
            if bidder_raw == "UNKNOWN_BIDDER":
                parse_confidence -= 0.4
            if item["is_totals_row"]:
                parse_confidence -= 0.1

            record = {
                "schema_version": SCHEMA_VERSION,
                "extract_run_id": run_id,
                "source_file": path.name,
                "source_sheet": ws.title,
                "source_row_index": item["source_row_index"],
                "source_table_header_row": structure.table_header_row,
                **header,
                **schedule,
                "line_no": item.get("line_no", ""),
                "item_description_raw": item.get("item_description_raw", ""),
                "item_description_clean": item.get("item_description_clean", ""),
                "item_code_raw": item.get("item_code_raw", ""),
                "item_code_norm": item.get("item_code_norm", ""),
                "section_code_raw": item.get("section_code_raw", ""),
                "section_code_norm": item.get("section_code_norm", ""),
                "quantity": item.get("quantity"),
                "unit_code_raw": item.get("unit_code_raw", ""),
                "unit_code_norm": item.get("unit_code_norm", ""),
                "bidder_name_raw": bidder_raw,
                "bidder_name_canonical": bidder_canon,
                "bidder_type": bidder_type,
                "is_engineers_estimate": is_est,
                "unit_price": item.get("unit_price"),
                "total_price": item.get("total_price"),
                "total_price_calc": None,
                "price_valid_flag": False if is_est else True,
                "parse_confidence": max(0.0, min(1.0, parse_confidence)),
                "is_totals_row": item.get("is_totals_row", False),
                "totals_row_label": item.get("totals_row_label", ""),
                "schedule_total": item.get("schedule_total"),
                "specification": item.get("specification", ""),
                "alternate_specification": item.get("alternate_specification", ""),
                "pay_item_description": item.get("pay_item_description", ""),
                "supplemental_description": item.get("supplemental_description", ""),
                "item": item.get("item", ""),
            }
            records.append(coerce_compiled_record(record))

    return records


def main():
    parser = argparse.ArgumentParser(description="Extract bid tab Excel files into compiled canonical csv (v2).")
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_csv", required=True)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--reports_dir", default="./reports")
    parser.add_argument("--config_dir", default="./config")
    parser.add_argument("--arith_tolerance", type=float, default=0.02)
    parser.add_argument("--totals_tolerance_amount", type=float, default=5.0)
    parser.add_argument("--totals_tolerance_pct", type=float, default=0.02)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_csv = Path(args.output_csv)
    reports_dir = Path(args.reports_dir)
    name_map = load_name_map(args.config_dir)

    parse_issues: List[ParseIssue] = []
    all_records: List[dict] = []
    for path in sorted(input_dir.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        all_records.extend(extract_file(path, args.run_id, name_map, parse_issues))

    df = pd.DataFrame(all_records)
    if df.empty:
        df = pd.DataFrame(columns=compiled_columns())
    else:
        for col in compiled_columns():
            if col not in df.columns:
                df[col] = None
        df = df[compiled_columns()]

        line_mask = df["is_totals_row"] == False  # noqa: E712
        for col in ["quantity", "unit_price", "total_price"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df.loc[line_mask, "total_price_calc"] = df.loc[line_mask, "unit_price"] * df.loc[line_mask, "quantity"]

        delta = (df["total_price"] - df["total_price_calc"]).abs()
        threshold = df["total_price"].abs().fillna(0).clip(lower=1) * float(args.arith_tolerance)
        calc_valid = (delta <= threshold) | df["total_price"].isna() | df["unit_price"].isna() | df["quantity"].isna()
        df.loc[line_mask & (~df["is_engineers_estimate"].astype(bool)), "price_valid_flag"] = calc_valid
        df.loc[df["is_engineers_estimate"].astype(bool), "price_valid_flag"] = False

        # enforce required string-null policy: no literal NA/null
        str_cols = [c for c in compiled_columns() if df[c].dtype == "object"]
        for c in str_cols:
            df[c] = df[c].fillna("").astype(str)
            df[c] = df[c].replace({"nan": "", "None": "", "NA": "", "null": ""})

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False, na_rep="")

    write_parse_summary(parse_issues, reports_dir / "qa_parse_summary.csv")
    if not df.empty:
        write_qa_reports(
            df,
            reports_dir,
            tolerance=float(args.arith_tolerance),
            tolerance_amount=float(args.totals_tolerance_amount),
            tolerance_pct=float(args.totals_tolerance_pct),
        )
        dupes = enforce_canonical_key_uniqueness(df)
        if not dupes.empty:
            parse_issues.append(ParseIssue("*", "*", "canonical_key_duplicates", f"rows={len(dupes)}"))
            write_parse_summary(parse_issues, reports_dir / "qa_parse_summary.csv")


if __name__ == "__main__":
    main()
