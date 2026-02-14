import pandas as pd

from scripts.build_star_schema import build_dim_project


def test_location_token_maps_to_expected_code():
    df = pd.DataFrame(
        [
            {
                "project_ean": "EAN-1",
                "solicitation_no": "SOL-1",
                "project_name_raw": "Test Project",
                "letting_date": "2026-01-01",
                "location_name_raw": "HILLSBOROAIRPORT",
                "source_file": "file.xlsx",
            },
            {
                "project_ean": "EAN-2",
                "solicitation_no": "SOL-2",
                "project_name_raw": "Test Project 2",
                "letting_date": "2026-01-02",
                "location_name_raw": "TERMINAL5",
                "source_file": "file2.xlsx",
            },
        ]
    )

    location_dict = pd.DataFrame(
        [
            {"location_name_raw": "HILLSBOROAIRPORT", "location_code": "HIO"},
            {"location_name_raw": "TERMINAL5", "location_code": "T5"},
        ]
    )

    dim = build_dim_project(df, location_dict)
    mapped = {r["location_name_raw"]: r["location_code"] for _, r in dim.iterrows()}
    assert mapped["HILLSBOROAIRPORT"] == "HIO"
    assert mapped["TERMINAL5"] == "T5"
