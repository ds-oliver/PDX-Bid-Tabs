#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import List

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.io_excel import load_workbook_data
from bidtabs.normalize import clean_whitespace
from bidtabs.parse_header import parse_project_header
from bidtabs.parse_table import detect_schedule_fields, parse_table_structure

TOTALS_PATTERN = re.compile(r"(total amount|basis of award)", re.IGNORECASE)

RAW_SNAPSHOT_COLUMNS = [
    "source_file",
    "source_sheet",
    "source_row_index",
    "source_table_header_row",
    "project_ean",
    "solicitation_no",
    "letting_date_raw",
    "location_name_raw",
    "project_name_raw",
    "bid_schedule_name",
    "bid_schedule_type",
    "bid_schedule_code",
    "line_no",
    "item_description_raw",
    "quantity_raw",
    "unit_code_raw",
    "unit_price_raw",
    "total_price_raw",
    "bidder_name_raw",
    "is_totals_row",
    "totals_row_label",
    "schedule_total_raw",
]


def _extract_line_no(ws, row: int, col: int) -> str:
    cell = ws.cell(row=row, column=col)
    raw = cell.value
    if raw is None:
        return ""
    if isinstance(raw, str):
        return clean_whitespace(raw)
    if isinstance(raw, (int, float)):
        num_format = clean_whitespace(cell.number_format)
        if num_format and set(num_format) <= {"0"}:
            width = len(num_format)
            try:
                return str(int(raw)).zfill(width)
            except Exception:
                pass
        if int(raw) == raw:
            return str(int(raw))
    return clean_whitespace(raw)


def _raw_text(value) -> str:
    return clean_whitespace(value)


def _detect_candidate_sheet(ws) -> bool:
    item_rows = 0
    for r in range(1, ws.max_row + 1):
        row_vals = [clean_whitespace(ws.cell(row=r, column=c).value).lower() for c in range(1, ws.max_column + 1)]
        if "item no." in row_vals or "item no" in row_vals:
            unit_count = row_vals.count("unit price")
            total_count = row_vals.count("total price")
            if unit_count >= 2 and total_count >= 2:
                item_rows += 1
    return item_rows >= 1


def _iter_rows(ws, table_header_row: int, col_map: dict, bidder_blocks: list, source_file: str, source_sheet: str, header: dict, schedule: dict):
    blank_streak = 0
    row = table_header_row + 1

    while row <= ws.max_row:
        line_no = _extract_line_no(ws, row, col_map["line_no_col"])
        desc_raw = _raw_text(ws.cell(row=row, column=col_map["desc_col"]).value)
        qty_raw = _raw_text(ws.cell(row=row, column=col_map["qty_col"]).value)
        unit_raw = _raw_text(ws.cell(row=row, column=col_map["unit_col"]).value)

        if not line_no and not desc_raw:
            blank_streak += 1
            if blank_streak >= 10:
                break
            row += 1
            continue

        blank_streak = 0
        is_totals = bool(TOTALS_PATTERN.search(desc_raw))
        if not (line_no or is_totals):
            row += 1
            continue

        for block in bidder_blocks:
            unit_raw_cell = _raw_text(ws.cell(row=row, column=block.unit_price_col).value)
            total_raw_cell = _raw_text(ws.cell(row=row, column=block.total_price_col).value)
            rec = {
                "source_file": source_file,
                "source_sheet": source_sheet,
                "source_row_index": row,
                "source_table_header_row": table_header_row,
                "project_ean": header.get("project_ean", ""),
                "solicitation_no": header.get("solicitation_no", ""),
                "letting_date_raw": header.get("letting_date_raw", ""),
                "location_name_raw": header.get("location_name_raw", ""),
                "project_name_raw": header.get("project_name_raw", ""),
                "bid_schedule_name": schedule.get("bid_schedule_name", ""),
                "bid_schedule_type": schedule.get("bid_schedule_type", ""),
                "bid_schedule_code": schedule.get("bid_schedule_code", ""),
                "line_no": "" if is_totals else line_no,
                "item_description_raw": desc_raw,
                "quantity_raw": "" if is_totals else qty_raw,
                "unit_code_raw": "" if is_totals else unit_raw,
                "unit_price_raw": "" if is_totals else unit_raw_cell,
                "total_price_raw": "" if is_totals else total_raw_cell,
                "bidder_name_raw": _raw_text(block.bidder_name_raw),
                "is_totals_row": bool(is_totals),
                "totals_row_label": desc_raw if is_totals else "",
                "schedule_total_raw": total_raw_cell if is_totals else "",
            }
            yield rec

        row += 1


def build_raw_snapshot(input_dir: Path) -> pd.DataFrame:
    records: List[dict] = []

    for path in sorted(input_dir.glob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        wb = load_workbook_data(path)

        for ws in wb.worksheets:
            if not _detect_candidate_sheet(ws):
                continue

            structure = parse_table_structure(ws)
            if structure.table_header_row < 0 or not structure.bidder_blocks:
                continue

            header = parse_project_header(ws, structure.table_header_row)
            schedule = detect_schedule_fields(ws.title)

            records.extend(
                _iter_rows(
                    ws,
                    structure.table_header_row,
                    structure.col_map,
                    structure.bidder_blocks,
                    path.name,
                    ws.title,
                    header,
                    schedule,
                )
            )

    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=RAW_SNAPSHOT_COLUMNS)

    for c in RAW_SNAPSHOT_COLUMNS:
        if c not in df.columns:
            df[c] = ""

    df = df[RAW_SNAPSHOT_COLUMNS].copy()
    df = df.sort_values(["source_file", "source_sheet", "source_row_index", "bidder_name_raw"], kind="stable").reset_index(drop=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build raw snapshot CSV at bidder-line grain directly from bid tab workbooks.")
    parser.add_argument("--input_dir", default="./data_in")
    parser.add_argument("--output_csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_csv = Path(args.output_csv)

    df = build_raw_snapshot(input_dir)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"Wrote {output_csv} ({len(df)} rows)")


if __name__ == "__main__":
    main()
