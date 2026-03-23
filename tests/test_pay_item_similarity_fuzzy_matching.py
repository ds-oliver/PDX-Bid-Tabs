from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.analyze_pay_item_similarity import build_high_variance_details


def test_unclassified_row_gets_expected_top_match():
    detail = pd.DataFrame(
        [
            {
                "Project EAN": "A",
                "Item Sequence": "1",
                "Item Description Raw": "120-Inch Manhole",
                "Item": "UNCLASSIFIED - Manhole",
                "Specification": "UNCLASSIFIED",
                "Alternate Specification": "",
                "Pay Item Description": "Manhole",
                "Supplemental Description": "120-Inch",
                "Unit": "EACH",
                "Unit Price": 100.0,
            },
            {
                "Project EAN": "B",
                "Item Sequence": "2",
                "Item Description Raw": "120-Inch Manhole (Sections 012200 and 334100)",
                "Item": "012200 - Manhole",
                "Specification": "012200",
                "Alternate Specification": "334100",
                "Pay Item Description": "Manhole",
                "Supplemental Description": "120-Inch",
                "Unit": "EACH",
                "Unit Price": 200.0,
            },
            {
                "Project EAN": "C",
                "Item Sequence": "3",
                "Item Description Raw": "24-Inch Storm Pipe (Section 334100)",
                "Item": "334100 - Storm Pipe",
                "Specification": "334100",
                "Alternate Specification": "",
                "Pay Item Description": "Storm Pipe",
                "Supplemental Description": "24-Inch",
                "Unit": "LF",
                "Unit Price": 50.0,
            },
        ]
    )

    summary = pd.DataFrame(
        [
            {"Specification": "UNCLASSIFIED", "Variance Level": "HIGH"},
            {"Specification": "012200", "Variance Level": "HIGH"},
            {"Specification": "334100", "Variance Level": "HIGH"},
        ]
    )

    high = build_high_variance_details(detail, summary)
    row = high[high["Specification"] == "UNCLASSIFIED"].iloc[0]
    assert row["Matching Spec 1"] == "012200 - Manhole"
