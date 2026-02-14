from pathlib import Path

import pandas as pd
from openpyxl import load_workbook

from scripts.build_dashboard_field_mapping import HEADERS


def test_dashboard_field_mapping_artifacts_exist_and_headers():
    import subprocess
    import sys

    subprocess.check_call([
        sys.executable,
        "scripts/build_dashboard_field_mapping.py",
        "--out_xlsx",
        "./docs/dashboard_field_mapping.xlsx",
    ])

    xlsx = Path("docs/dashboard_field_mapping.xlsx")
    assert xlsx.exists()

    wb = load_workbook(xlsx, data_only=True)
    assert wb.sheetnames == ["README", "Field_Mapping"]

    ws = wb["Field_Mapping"]
    got = [ws.cell(1, i).value for i in range(1, len(HEADERS) + 1)]
    assert got == HEADERS


def test_mapping_rows_match_expected_content():
    df = pd.read_excel("docs/dashboard_field_mapping.xlsx", sheet_name="Field_Mapping")
    expected_sources = {
        "Letting Date": "Projects.Advertise_Date",
        "District & County": "Projects.Location",
        "Specification": "Items.Specification_Code",
        "Item Description": "Items.Item_Description",
        "Awarded Item Price": "Bids.Unit_Price (filtered by Is_Winner)",
        "Average Item Price (3 Lowest)": "Measure (Calculated in Power BI)",
        "Quantity": "Items.Estimated_Quantity",
        "Unit": "Items.Unit",
        "Project Number": "Projects.EAN",
        "Contractor": "Bids.Contractor_Name",
        "Prop Line No.": "Items.Item_Sequence",
        "Project Title": "Projects.Project_Name",
        "Project Total": "Bids.Total_Price (Sum)",
        "Project Type": "Not currently captured",
        "Supplemental Description": "Not currently captured",
        "Percent of Project Total": "Calculated in Power BI",
    }
    assert len(df) == len(expected_sources)

    for odot, src in expected_sources.items():
        row = df[df["ODOT Report Field"] == odot]
        assert not row.empty
        assert row.iloc[0]["Port Report Field Source"] == src

    readme = load_workbook("docs/dashboard_field_mapping.xlsx", data_only=True)["README"]
    assert readme["A1"].value == "Purpose:"
    assert "ODOT Bid Data Reporting standard" in str(readme["A5"].value)
