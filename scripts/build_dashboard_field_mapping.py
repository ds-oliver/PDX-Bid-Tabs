#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


HEADERS = [
    "ODOT Report Field",
    "Port Report Field Name",
    "Port Report Field Source",
    "Example Raw (Bid Tab Sheet)",
    "Example Normalized",
]


def build_mapping_df() -> pd.DataFrame:
    rows = [
        ["Letting Date", "Advertise Date", "Projects.Advertise_Date", "2/11/26", "2026"],
        ["District & County", "Location", "Projects.Location", "PORTLAND INTERNATIONAL AIRPORT", "PDX"],
        ["Specification", "Specification Code", "Items.Specification_Code", "(Item P-620)", "P-620"],
        ["Item Description", "Pay Item Description", "Items.Item_Description", "Marking (Item P-620)", "Marking"],
        ["Awarded Item Price", "Unit Price", "Bids.Unit_Price (filtered by Is_Winner)", "$3.90", "3.90"],
        ["Average Item Price (3 Lowest)", "Average Unit Price (Top 3)", "Measure (Calculated in Power BI)", "Calculated", "Calculated"],
        ["Quantity", "Estimated Quantity", "Items.Estimated_Quantity", "5,407.0", "5,407"],
        ["Unit", "Units", "Items.Unit", "SY", "SY"],
        ["Project Number", "EAN", "Projects.EAN", "EAN 2023D018", "2023D018"],
        ["Contractor", "Contractor", "Bids.Contractor_Name", "Fortis Construction", "Fortis Construction"],
        ["Prop Line No.", "Item Sequence", "Items.Item_Sequence", "0004", "0004"],
        ["Project Title", "Project Name", "Projects.Project_Name", "EGSE INFRASTRUCTURE INSTALLATION - PHASE 2 0", "EGSE INFRASTRUCTURE INSTALLATION - PHASE 2 0"],
        ["Project Total", "Total Amount Bid", "Bids.Total_Price (Sum)", "$6,387,362.33", "Calculated"],
        ["Project Type", "N/A", "Not currently captured", "N/A", "N/A"],
        ["Supplemental Description", "N/A", "Not currently captured", "N/A", "N/A"],
        ["Percent of Project Total", "N/A", "Calculated in Power BI", "N/A", "N/A"],
    ]
    return pd.DataFrame(rows, columns=HEADERS)


def write_xlsx(df_map: pd.DataFrame, out_xlsx: Path) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        wb = writer.book

        # README sheet
        readme = wb.add_worksheet("README")
        writer.sheets["README"] = readme
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})
        bold = wb.add_format({"bold": True})

        readme.write("A1", "Purpose:", bold)
        readme.write("A2", "This document maps the user-facing fields in the Power BI Dashboard to the underlying Port of Portland data sources.", wrap)

        readme.write("A4", "Scope:", bold)
        readme.write("A5", "Based on the ODOT Bid Data Reporting standard, adapted for Port-specific terminologies (e.g., EAN, Advertise Date).", wrap)

        readme.write("A7", "Legend:", bold)
        readme.write("A8", "Raw: Data exactly as it appears in the source bid tab sheet.", wrap)
        readme.write("A9", "Normalized: Data cleaned by the ETL process (e.g., stripping codes from descriptions).", wrap)

        readme.write("A11", "Terminology Standard:", bold)
        readme.write("A12", "Specification Code: extracted grouping code (e.g., P-620, 012200).", wrap)
        readme.write("A13", "Pay Item Description: description text minus extracted code.", wrap)
        readme.write("A14", "Raw Line Item Description: original full line text from bid tab.", wrap)
        readme.write("A15", "Pay Item: unique combination of Specification Code + Pay Item Description + Unit.", wrap)

        readme.set_column("A:A", 130)

        # Field_Mapping sheet
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
                "name": "FieldMappingTable",
                "style": "Table Style Medium 2",
                "columns": [{"header": c} for c in df_map.columns],
            },
        )

        wrap_fmt = wb.add_format({"text_wrap": True, "valign": "top"})
        for i, col in enumerate(df_map.columns):
            max_len = max(len(str(col)), int(df_map[col].astype(str).map(len).max()) if len(df_map) else 0)
            ws.set_column(i, i, min(max_len + 2, 80), wrap_fmt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dashboard field mapping workbook.")
    parser.add_argument("--out_xlsx", default="./docs/dashboard_field_mapping.xlsx")
    args = parser.parse_args()

    df_map = build_mapping_df()
    write_xlsx(df_map, Path(args.out_xlsx))


if __name__ == "__main__":
    main()
