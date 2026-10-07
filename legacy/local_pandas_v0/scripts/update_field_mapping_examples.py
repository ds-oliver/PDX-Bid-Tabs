#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from bidtabs.parse_items import parse_item_fields

OUT_HEADERS = [
    "ODOT Report Object",
    "Port Data Object",
    "Report Feature",
    "Example (ODOT)",
    "Example (Port)",
    "Port Data Object Source",
    "ODOT Example Source",
    "Mapping Status",
    "Dev Notes",
]

ALLOWED_REPORT_FEATURE = {"Slicer", "Table", "Table,Slicer", "NA"}
ALLOWED_MAPPING_STATUS = {"Mapped", "Best Guess", "Port Only", "ODOT Only"}
BEST_GUESS_OBJECTS = {"Item", "Specification", "Supplemental Description"}
BEST_GUESS_NOTE = (
    "Port requested follow-up: 'Let's talk about these after you look at the data.' "
    "Current Port equivalents/examples are best-guess mappings and not yet confirmed."
)

RAW_SOURCE_RULES = {
    "source_file": "Extraction metadata: workbook filename",
    "source_sheet": "Extraction metadata: worksheet title",
    "source_row_index": "Extraction metadata: worksheet row number",
    "source_table_header_row": "Extraction metadata: detected table header row",
    "project_ean": "Bid Tab Header: EAN",
    "solicitation_no": "Bid Tab Header: Solicitation No.",
    "letting_date_raw": "Bid Tab Header: Letting Date",
    "location_name_raw": "Bid Tab Header: Location/Facility",
    "project_name_raw": "Bid Tab Header: Project Title",
    "bid_schedule_name": "Sheet Context: schedule/sheet label",
    "bid_schedule_type": "Sheet Context: BASE vs ALTERNATE heuristic",
    "bid_schedule_code": "Sheet Context: schedule code token (if present)",
    "line_no": "Line Item Column: Item No.",
    "item_description_raw": "Line Item Column: Item Description",
    "quantity_raw": "Line Item Column: Estimated Quantity",
    "unit_code_raw": "Line Item Column: Units",
    "unit_price_raw": "Bidder Columns: Unit Price",
    "total_price_raw": "Bidder Columns: Total Price",
    "bidder_name_raw": "Bidder Header: Contractor label above Unit/Total columns",
    "is_totals_row": "Derived flag from totals-row detection pattern",
    "totals_row_label": "Line Item Description on totals rows",
    "schedule_total_raw": "Totals Row: Total Amount Bid (Basis of Award)",
}

EXCLUDED_PORT_ONLY_OBJECTS = {
    "source_file",
    "source_sheet",
    "source_row_index",
    "source_table_header_row",
    "is_totals_row",
    "bid_schedule_name",
    "bid_schedule_type",
    "bid_schedule_code",
    "totals_row_label",
}


def _first_row(df: pd.DataFrame, mask: pd.Series) -> pd.Series | None:
    x = df[mask].copy()
    if x.empty:
        return None
    cols = [c for c in ["source_file", "source_sheet", "source_row_index"] if c in x.columns]
    if cols:
        x = x.sort_values(cols, kind="stable")
    return x.iloc[0]


def _get_col(df: pd.DataFrame, candidates: list[str]) -> pd.Series:
    for c in candidates:
        if c in df.columns:
            return df[c]
    return pd.Series([""] * len(df), index=df.index)


def _first_non_empty(df: pd.DataFrame, col: str) -> str:
    if col not in df.columns:
        return "N/A"
    s = df[col].astype(str).str.strip()
    s = s[s != ""]
    if s.empty:
        return "N/A"
    return str(s.iloc[0])


def _sheet_frame(df: pd.DataFrame) -> pd.DataFrame:
    if "is_totals_row" not in df.columns:
        return df
    line = df[~df["is_totals_row"].astype(str).str.lower().isin(["true", "1"])].copy()
    if line.empty:
        return df
    first = line.sort_values(["source_file", "source_sheet", "source_row_index"], kind="stable").iloc[0]
    return df[(df["source_file"] == first["source_file"]) & (df["source_sheet"] == first["source_sheet"])].copy()


def _example_from_rule(rule: str, raw_df: pd.DataFrame, clean_df: pd.DataFrame | None) -> str:
    if not rule or str(rule).strip().lower() in {"", "na", "n/a"}:
        return "N/A"

    sheet_raw = _sheet_frame(raw_df)

    if rule.startswith("col:"):
        col = rule.split(":", 1)[1].strip()
        val = _first_non_empty(sheet_raw, col)
        if val == "N/A":
            val = _first_non_empty(raw_df, col)
        return val

    if rule == "contractor":
        s = _get_col(sheet_raw, ["bidder_name_raw"]).astype(str)
        s = s[(s.str.strip() != "") & (~s.str.contains("engineer", case=False, na=False))]
        return str(s.iloc[0]) if not s.empty else "N/A"

    if rule == "avg_top3":
        line = raw_df[~_get_col(raw_df, ["is_totals_row"]).astype(str).str.lower().isin(["true", "1"])].copy()
        prices = pd.to_numeric(_get_col(line, ["unit_price_raw", "unit_price"]), errors="coerce")
        bidders = _get_col(line, ["bidder_name_raw", "bidder_name_canonical"]).astype(str)
        line = line[(~bidders.str.contains("engineer", case=False, na=False)) & prices.notna()].copy()
        line["_unit_price"] = pd.to_numeric(_get_col(line, ["unit_price_raw", "unit_price"]), errors="coerce")
        if line.empty:
            return "N/A"
        g = line.groupby(["source_file", "source_sheet", "line_no"], dropna=False)
        for _, part in g:
            vals = part["_unit_price"].nsmallest(3)
            if len(vals):
                return f"{vals.mean():.2f}"
        return "N/A"

    if rule == "number_bidders":
        line = sheet_raw[~_get_col(sheet_raw, ["is_totals_row"]).astype(str).str.lower().isin(["true", "1"])].copy()
        names = _get_col(line, ["bidder_name_raw", "bidder_name_canonical"]).astype(str)
        names = names[(names.str.strip() != "") & (~names.str.contains("engineer", case=False, na=False))]
        if names.empty:
            return "N/A"
        return str(names.nunique())

    if rule in {"item_best_guess", "specification_best_guess", "supplemental_best_guess"}:
        if clean_df is not None and not clean_df.empty:
            clean_sheet = _sheet_frame(clean_df)
            line = clean_sheet[~_get_col(clean_sheet, ["is_totals_row"]).astype(str).str.lower().isin(["true", "1"])].copy()
            if rule == "item_best_guess":
                v = _first_non_empty(line, "item")
                if v != "N/A":
                    return v
            if rule == "specification_best_guess":
                v = _first_non_empty(line, "specification")
                if v != "N/A":
                    return v
            if rule == "supplemental_best_guess":
                v = _first_non_empty(line, "supplemental_description")
                if v != "N/A":
                    return v

        line_raw = sheet_raw[~_get_col(sheet_raw, ["is_totals_row"]).astype(str).str.lower().isin(["true", "1"])].copy()
        desc = _first_non_empty(line_raw, "item_description_raw")
        if desc == "N/A":
            return "N/A"
        parsed = parse_item_fields(desc)
        if rule == "item_best_guess":
            return parsed.get("item_display", "N/A") or "N/A"
        if rule == "specification_best_guess":
            return parsed.get("spec_code_primary", "N/A") or "N/A"
        return parsed.get("supplemental_description", "") or "N/A"

    return "N/A"


def _append_missing_port_objects(df_src: pd.DataFrame, raw_df: pd.DataFrame) -> pd.DataFrame:
    if raw_df.empty:
        return df_src

    existing = set(df_src["Port Data Object"].astype(str).str.strip())
    additions = []
    for col in raw_df.columns:
        if col in EXCLUDED_PORT_ONLY_OBJECTS:
            continue
        if col in existing:
            continue
        additions.append(
            {
                "ODOT Report Object": "NA",
                "Port Data Object": col,
                "Report Feature": "NA",
                "Example (ODOT)": "NA",
                "ODOT Example Source": "NA",
                "Port Data Object Source": RAW_SOURCE_RULES.get(col, "Bid Tab Extract Field"),
                "Mapping Status": "Port Only",
                "Dev Notes": "Included for completeness/traceability; not in current dashboard requirements.",
                "example_rule": f"col:{col}",
                "Example (Port)": "",
            }
        )

    if additions:
        df_src = pd.concat([df_src, pd.DataFrame(additions)], ignore_index=True)
    return df_src


def build_mapping(source_csv: Path, raw_csv: Path, clean_csv: Path | None = None) -> pd.DataFrame:
    src = pd.read_csv(source_csv, keep_default_na=False)
    raw_df = pd.read_csv(raw_csv, keep_default_na=False)
    clean_df = None
    if clean_csv is not None and clean_csv.exists():
        clean_df = pd.read_csv(clean_csv, keep_default_na=False)

    src = _append_missing_port_objects(src, raw_df)

    rows = []
    for _, r in src.iterrows():
        odot_obj = str(r.get("ODOT Report Object", "")).strip() or "NA"
        port_obj = str(r.get("Port Data Object", "")).strip()
        report_feature = str(r.get("Report Feature", "NA")).strip() or "NA"
        mapping_status = str(r.get("Mapping Status", "Mapped")).strip() or "Mapped"
        dev_notes = str(r.get("Dev Notes", "")).strip()

        if odot_obj in BEST_GUESS_OBJECTS:
            mapping_status = "Best Guess"
            dev_notes = BEST_GUESS_NOTE

        if report_feature not in ALLOWED_REPORT_FEATURE:
            report_feature = "NA"
        if mapping_status not in ALLOWED_MAPPING_STATUS:
            mapping_status = "Mapped"

        ex_port = str(r.get("Example (Port)", "")).strip()
        if not ex_port:
            ex_port = _example_from_rule(str(r.get("example_rule", "")).strip(), raw_df, clean_df)

        rows.append(
            {
                "ODOT Report Object": odot_obj,
                "Port Data Object": port_obj,
                "Report Feature": report_feature,
                "Example (ODOT)": str(r.get("Example (ODOT)", "")).strip() or "NA",
                "Example (Port)": ex_port if ex_port else "N/A",
                "Port Data Object Source": str(r.get("Port Data Object Source", "")).strip() or "N/A",
                "ODOT Example Source": str(r.get("ODOT Example Source", "")).strip() or "NA",
                "Mapping Status": mapping_status,
                "Dev Notes": dev_notes,
            }
        )

    df = pd.DataFrame(rows, columns=OUT_HEADERS)

    odot_mask = df["ODOT Report Object"].astype(str) != "NA"
    df_odot = df[odot_mask].copy()
    df_port_only = df[~odot_mask].copy().sort_values(["Port Data Object"], kind="stable")
    return pd.concat([df_odot, df_port_only], ignore_index=True)


def write_xlsx(df: pd.DataFrame, out_path: Path, sheet_name: str = "ODOT_to_Port_Mapping") -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
        ws = writer.sheets[sheet_name]
        wb = writer.book
        ws.add_table(
            0,
            0,
            len(df),
            len(df.columns) - 1,
            {
                "name": "ODOTPortMapping",
                "style": "Table Style Medium 2",
                "columns": [{"header": c} for c in df.columns],
            },
        )
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        for i, c in enumerate(df.columns):
            max_len = max(len(c), int(df[c].astype(str).map(len).max()) if len(df) else 0)
            ws.set_column(i, i, min(max_len + 2, 90), wrap)


def write_md(df: pd.DataFrame, out_path: Path, title: str = "ODOT to Port Field Mapping") -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {title}",
        "",
        "How to update:",
        "1. Update `docs/data_dictionary/odot_to_port_field_mapping_source.csv`.",
        "2. Run `python scripts/update_field_mapping_examples.py`.",
        "3. Commit both XLSX and MD outputs together.",
        "",
        "| " + " | ".join(df.columns) + " |",
        "|" + "|".join(["---"] * len(df.columns)) + "|",
    ]
    for _, r in df.iterrows():
        vals = [str(r[c]).replace("\n", " ") for c in df.columns]
        lines.append("| " + " | ".join(vals) + " |")
    out_path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update ODOT-to-Port mapping files with object-level examples.")
    parser.add_argument("--source_csv", default="./docs/data_dictionary/odot_to_port_field_mapping_source.csv")
    parser.add_argument("--raw_csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    parser.add_argument("--clean_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--out_xlsx", default="./docs/data_dictionary/odot_to_port_field_mapping.xlsx")
    parser.add_argument("--out_md", default="./docs/data_dictionary/odot_to_port_field_mapping.md")
    args = parser.parse_args()

    clean_path = Path(args.clean_csv)
    df = build_mapping(Path(args.source_csv), Path(args.raw_csv), clean_path if clean_path.exists() else None)
    write_xlsx(df, Path(args.out_xlsx))
    write_md(df, Path(args.out_md))
    print(f"Wrote {args.out_xlsx}")
    print(f"Wrote {args.out_md}")


if __name__ == "__main__":
    main()
