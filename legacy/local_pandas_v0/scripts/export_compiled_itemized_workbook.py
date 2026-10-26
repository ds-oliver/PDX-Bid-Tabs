#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from bidtabs.schemas import business_export_columns


def _to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def _derive_advertise_date(df: pd.DataFrame) -> pd.Series:
    dt = pd.to_datetime(df.get("letting_date", ""), errors="coerce")
    out = dt.dt.strftime("%Y-%m-%d").fillna("")
    # fallback to raw token if parsed date missing
    raw = df.get("letting_date_raw", pd.Series("", index=df.index)).astype(str)
    out = out.where(out != "", raw)
    return out


def _build_business_frames(df: pd.DataFrame):
    _, order, mapping = business_export_columns()

    work = df.copy()
    work["Advertise Date"] = _derive_advertise_date(work)

    for src, dst in mapping.items():
        if src in work.columns:
            work[dst] = work[src]
        elif dst not in work.columns:
            work[dst] = ""

    is_totals = _to_bool(work.get("is_totals_row", pd.Series(False, index=work.index)))

    line_items = work.loc[~is_totals, order].copy()
    schedule_totals = pd.DataFrame(
        {
            "Advertise Date": work.loc[is_totals, "Advertise Date"],
            "Location": work.loc[is_totals, "Location"],
            "Project Name": work.loc[is_totals, "Project Name"],
            "EAN": work.loc[is_totals, "EAN"],
            "Bid Schedule Name": work.loc[is_totals, "Bid Schedule Name"],
            "Bid Schedule Type": work.loc[is_totals, "Bid Schedule Type"],
            "Bid Schedule Code": work.loc[is_totals, "Bid Schedule Code"],
            "Contractor": work.loc[is_totals, "Contractor"],
            "Is Engineer's Estimate": work.loc[is_totals, "Is Engineer's Estimate"],
            "Total Amount Bid": work.loc[is_totals, "schedule_total"] if "schedule_total" in work.columns else "",
            "Totals Row Label": work.loc[is_totals, "totals_row_label"] if "totals_row_label" in work.columns else "",
        }
    )

    # Ensure order and uniqueness for totals rows.
    schedule_totals = schedule_totals.drop_duplicates().reset_index(drop=True)

    return line_items, schedule_totals


def _build_column_dictionary_df() -> pd.DataFrame:
    defs, _, _ = business_export_columns()
    rows = [
        {
            "column_name": c.name,
            "dtype": c.dtype,
            "nullable": c.nullable,
            "definition": c.description,
            "source_rule": c.source_rule,
        }
        for c in defs
    ]
    rows.extend(
        [
            {
                "column_name": "Total Amount Bid",
                "dtype": "float",
                "nullable": True,
                "definition": "Bid total from schedule totals row for bidder context.",
                "source_rule": "schedule_total on totals rows",
            },
            {
                "column_name": "Totals Row Label",
                "dtype": "str",
                "nullable": True,
                "definition": "Original totals row description label from sheet.",
                "source_rule": "totals_row_label on totals rows",
            },
        ]
    )
    return pd.DataFrame(rows)


def _write_readme(ws, wb, line_count: int, totals_count: int, col_count: int) -> None:
    bold = wb.add_format({"bold": True})
    wrap = wb.add_format({"text_wrap": True, "valign": "top"})

    lines = [
        ("A1", "Purpose", True),
        (
            "A2",
            "This workbook is the business-facing compiled itemized extract for dashboard/reporting use. It exposes only business fields and separates line items from schedule totals.",
            False,
        ),
        ("A4", "How We Compiled It", True),
        ("A5", "1) Parse Excel bid tab sheets for header context, bidder blocks, line items, and totals rows.", False),
        ("A6", "2) Parse Item Description into Specification, Alternate Specification, Pay Item Description, Supplemental Description, and Item.", False),
        ("A7", "3) Normalize bidder names, units, and dates where possible.", False),
        ("A8", "4) Output line-level bidder rows and separate schedule totals rows.", False),
        ("A10", "Assumptions", True),
        ("A11", "Item is constructed as <Specification> - <Pay Item Description>.", False),
        ("A12", "Alternate Specification is populated when plural Sections contain multiple codes.", False),
        ("A13", "Totals are not mixed into line items; they are in Schedule_Totals.", False),
        ("A14", "This extract is sheet-native bid data and does not assert award/acceptance outcomes.", False),
        ("A16", "Snapshot", True),
        ("A17", f"Line item rows: {line_count:,}", False),
        ("A18", f"Schedule totals rows: {totals_count:,}", False),
        ("A19", f"Business columns (Line_Items): {col_count}", False),
        ("A21", "Column definitions", True),
        ("A22", "See Column_Definitions for field definitions and source mapping.", False),
    ]

    for cell, text, is_bold in lines:
        ws.write(cell, text, bold if is_bold else wrap)

    ws.set_column("A:A", 145, wrap)


def export_workbook(input_csv: Path, output_xlsx: Path) -> None:
    df = pd.read_csv(input_csv, keep_default_na=False)
    line_items, totals = _build_business_frames(df)
    col_df = _build_column_dictionary_df()

    output_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_xlsx, engine="xlsxwriter") as writer:
        wb = writer.book

        readme = wb.add_worksheet("README")
        writer.sheets["README"] = readme
        _write_readme(readme, wb, len(line_items), len(totals), len(line_items.columns))

        col_df.to_excel(writer, index=False, sheet_name="Column_Definitions")
        ws_cols = writer.sheets["Column_Definitions"]
        ws_cols.freeze_panes(1, 0)
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        for i, c in enumerate(col_df.columns):
            max_len = max(len(c), int(col_df[c].astype(str).map(len).max()) if len(col_df) else 0)
            ws_cols.set_column(i, i, min(max_len + 2, 95), wrap)

        line_items.to_excel(writer, index=False, sheet_name="Line_Items")
        ws_line = writer.sheets["Line_Items"]
        ws_line.freeze_panes(1, 0)
        for i, c in enumerate(line_items.columns):
            max_len = max(len(c), int(line_items[c].astype(str).map(len).max()) if len(line_items) else 0)
            ws_line.set_column(i, i, min(max_len + 2, 48))

        totals.to_excel(writer, index=False, sheet_name="Schedule_Totals")
        ws_tot = writer.sheets["Schedule_Totals"]
        ws_tot.freeze_panes(1, 0)
        for i, c in enumerate(totals.columns):
            max_len = max(len(c), int(totals[c].astype(str).map(len).max()) if len(totals) else 0)
            ws_tot.set_column(i, i, min(max_len + 2, 48))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export business-facing compiled itemized workbook with README and column definitions.")
    parser.add_argument("--input_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--output_xlsx", default="./data_out/compiled_excel_itemized_clean.xlsx")
    args = parser.parse_args()

    export_workbook(Path(args.input_csv), Path(args.output_xlsx))
    print(f"Wrote {args.output_xlsx}")


if __name__ == "__main__":
    main()
