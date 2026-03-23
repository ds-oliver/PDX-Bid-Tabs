#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from update_field_mapping_examples import build_mapping


def write_xlsx(df_map: pd.DataFrame, out_xlsx: Path) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        wb = writer.book
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        bold = wb.add_format({"bold": True})

        readme = wb.add_worksheet("README")
        writer.sheets["README"] = readme

        readme.write("A1", "Purpose", bold)
        readme.write(
            "A2",
            "Object-level mapping between ODOT report components and Port bid tabulation data objects.",
            wrap,
        )

        readme.write("A4", "Scope", bold)
        readme.write("A5", "Includes all ODOT-highlighted report components from provided screenshots.", wrap)
        readme.write("A6", "Includes all distinct extracted Port bid-tab objects for completeness and traceability.", wrap)
        readme.write("A7", "Rows with ODOT Report Object = NA are Port-only objects not currently required as dashboard features.", wrap)

        readme.write("A9", "Report Feature Definitions", bold)
        readme.write("A10", "Slicer: object is used as a filter/slicer control.", wrap)
        readme.write("A11", "Table: object is used as a table/grid output column.", wrap)
        readme.write("A12", "Table,Slicer: object is used in both contexts.", wrap)
        readme.write("A13", "NA: object is not part of current dashboard requirements.", wrap)

        readme.write("A15", "Mapping Status Definitions", bold)
        readme.write("A16", "Mapped: direct and accepted equivalence.", wrap)
        readme.write("A17", "Best Guess: likely equivalent but not confirmed.", wrap)
        readme.write("A18", "Port Only: exists in Port data but not represented as an ODOT report object.", wrap)
        readme.write("A19", "ODOT Only: exists in ODOT report but no Port equivalent identified.", wrap)

        readme.write("A21", "Confidence Caveat", bold)
        readme.write(
            "A22",
            "Item, Specification, and Supplemental Description are marked Best Guess per Port instruction: 'Let's talk about these after you look at the data.'",
            wrap,
        )

        readme.set_column("A:A", 145)

        sheet = "Field_Mapping"
        df_map.to_excel(writer, index=False, sheet_name=sheet)
        ws = writer.sheets[sheet]
        nrows, ncols = df_map.shape

        ws.add_table(
            0,
            0,
            nrows,
            ncols - 1,
            {
                "name": "DashboardFieldMapping",
                "style": "Table Style Medium 2",
                "columns": [{"header": c} for c in df_map.columns],
            },
        )

        for i, col in enumerate(df_map.columns):
            max_len = max(len(str(col)), int(df_map[col].astype(str).map(len).max()) if len(df_map) else 0)
            ws.set_column(i, i, min(max_len + 2, 95), wrap)


def write_md(df_map: pd.DataFrame, out_md: Path) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Dashboard Field Mapping",
        "",
        "Object-level mapping between ODOT report components and Port bid tabulation objects.",
        "Includes all ODOT-highlighted objects and all extracted Port objects for completeness.",
        "",
        "| " + " | ".join(df_map.columns) + " |",
        "|" + "|".join(["---"] * len(df_map.columns)) + "|",
    ]
    for _, row in df_map.iterrows():
        vals = [str(row[c]).replace("\n", " ") for c in df_map.columns]
        lines.append("| " + " | ".join(vals) + " |")
    out_md.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build object-level dashboard field mapping workbook.")
    parser.add_argument("--source_csv", default="./docs/data_dictionary/odot_to_port_field_mapping_source.csv")
    parser.add_argument("--raw_csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    parser.add_argument("--clean_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--out_xlsx", default="./docs/dashboard_field_mapping.xlsx")
    parser.add_argument("--out_md", default="./docs/dashboard_field_mapping.md")
    args = parser.parse_args()

    clean_path = Path(args.clean_csv)
    df_map = build_mapping(
        Path(args.source_csv),
        Path(args.raw_csv),
        clean_path if clean_path.exists() else None,
    )
    write_xlsx(df_map, Path(args.out_xlsx))
    write_md(df_map, Path(args.out_md))


if __name__ == "__main__":
    main()
