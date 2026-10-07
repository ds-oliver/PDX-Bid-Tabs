from pathlib import Path

import pandas as pd


EXPECTED_COLS = [
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


def test_raw_snapshot_artifacts_and_schema():
    import subprocess
    import sys

    subprocess.check_call([
        sys.executable,
        "scripts/build_raw_snapshot.py",
        "--input_dir",
        "./data_in",
        "--output_csv",
        "./data_out/compiled_excel_itemized_raw_snapshot.csv",
    ])

    path = Path("data_out/compiled_excel_itemized_raw_snapshot.csv")
    assert path.exists()

    df = pd.read_csv(path, keep_default_na=False)
    assert not df.empty
    assert list(df.columns) == EXPECTED_COLS

    # Ensure cleaned/derived internals are not present in the raw snapshot artifact.
    forbidden = {
        "parse_confidence",
        "item_description_clean",
        "pay_item_description",
        "supplemental_description",
        "specification",
        "alternate_specification",
        "item",
        "bidder_name_canonical",
    }
    assert forbidden.isdisjoint(df.columns)
