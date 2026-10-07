import pandas as pd

from bidtabs.model import build_analysis_tables


def test_bids_rowcount_stable_and_item_unique():
    canonical = pd.DataFrame(
        [
            {
                "project_ean": "P1",
                "solicitation_no": "S1",
                "project_name_raw": "Proj",
                "letting_date": "2026-01-01",
                "location_name_raw": "PDX",
                "source_file": "f.xlsx",
                "source_sheet": "Base Bid",
                "source_row_index": 10,
                "line_no": "0010",
                "item_description_raw": "Item A (Item C-105)",
                "item_description_clean": "Item A (Item C-105)",
                "item_code_norm": "C-105",
                "section_code_norm": "",
                "item_code_raw": "C-105",
                "section_code_raw": "",
                "unit_code_norm": "EA",
                "quantity": 2,
                "unit_price": 3,
                "total_price": 6,
                "bidder_type": "CONTRACTOR",
                "bidder_name_canonical": "ACME",
                "is_totals_row": False,
            },
            {
                "project_ean": "P1",
                "solicitation_no": "S1",
                "project_name_raw": "Proj",
                "letting_date": "2026-01-01",
                "location_name_raw": "PDX",
                "source_file": "f.xlsx",
                "source_sheet": "Base Bid",
                "source_row_index": 11,
                "line_no": "0010",
                "item_description_raw": "Item A (Item C-105)",
                "item_description_clean": "Item A (Item C-105)",
                "item_code_norm": "C-105",
                "section_code_norm": "",
                "item_code_raw": "C-105",
                "section_code_raw": "",
                "unit_code_norm": "EA",
                "quantity": 2,
                "unit_price": 4,
                "total_price": 8,
                "bidder_type": "CONTRACTOR",
                "bidder_name_canonical": "BRAVO",
                "is_totals_row": False,
            },
            {
                "project_ean": "P1",
                "solicitation_no": "S1",
                "project_name_raw": "Proj",
                "letting_date": "2026-01-01",
                "location_name_raw": "PDX",
                "source_file": "f.xlsx",
                "source_sheet": "Base Bid",
                "source_row_index": 12,
                "line_no": "0010",
                "item_description_raw": "Item A (Item C-105)",
                "item_description_clean": "Item A (Item C-105)",
                "item_code_norm": "C-105",
                "section_code_norm": "",
                "item_code_raw": "C-105",
                "section_code_raw": "",
                "unit_code_norm": "EA",
                "quantity": 2,
                "unit_price": 3.5,
                "total_price": 7,
                "bidder_type": "ENGINEERS_ESTIMATE",
                "bidder_name_canonical": "ENGINEER'S ESTIMATE",
                "is_totals_row": False,
            },
        ]
    )
    location_dict = pd.DataFrame(columns=["location_name_raw", "location_code"])

    tables = build_analysis_tables(canonical, location_dict)
    projects = tables["Projects"]
    items = tables["Items"]
    bids = tables["Bids"]

    assert len(projects) == 1
    assert len(items) == 1
    assert len(bids) == 3
    assert bids["bid_id"].is_unique

    # EE remains but is never winner and is unranked.
    ee = bids[bids["contractor_name"].str.contains("ENGINEER", case=False, na=False)].iloc[0]
    assert bool(ee["is_winner"]) is False
    assert ee["rank"] == ""

    # Lowest contractor should rank 1.
    acme = bids[bids["contractor_name"] == "ACME"].iloc[0]
    assert acme["rank"] == 1
