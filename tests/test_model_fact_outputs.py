import pandas as pd

from bidtabs.model import build_model


def _sample_clean_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "extract_run_id": "r1",
                "source_file": "f.xlsx",
                "source_sheet": "Base Bid",
                "source_row_index": 10,
                "project_ean": "P1",
                "solicitation_no": "S1",
                "project_name_raw": "Proj",
                "letting_date": "2026-01-01",
                "location_name_raw": "PDX",
                "bid_schedule_name": "Base Bid",
                "bid_schedule_type": "BASE",
                "bid_schedule_code": "",
                "line_no": "0010",
                "item_description_raw": "120-Inch Manhole (Sections 012200 and 334100)",
                "item_description_clean": "120-Inch Manhole",
                "specification": "012200",
                "alternate_specification": "334100",
                "pay_item_description": "Manhole",
                "supplemental_description": "120-Inch",
                "item": "012200 - Manhole",
                "item_code_raw": "",
                "item_code_norm": "",
                "section_code_raw": "012200",
                "section_code_norm": "012200",
                "unit_code_raw": "EA",
                "unit_code_norm": "EA",
                "quantity": 1,
                "bidder_name_raw": "ACME",
                "bidder_name_canonical": "ACME",
                "bidder_type": "CONTRACTOR",
                "is_engineers_estimate": False,
                "unit_price": 100.0,
                "total_price": 100.0,
                "price_valid_flag": True,
                "parse_confidence": 0.95,
                "is_totals_row": False,
            },
            {
                "extract_run_id": "r1",
                "source_file": "f.xlsx",
                "source_sheet": "ALT 1",
                "source_row_index": 12,
                "project_ean": "P1",
                "solicitation_no": "S1",
                "project_name_raw": "Proj",
                "letting_date": "2026-01-01",
                "location_name_raw": "PDX",
                "bid_schedule_name": "ALT 1",
                "bid_schedule_type": "ALTERNATE",
                "bid_schedule_code": "ALT_1",
                "line_no": "0010",
                "item_description_raw": "120-Inch Manhole (Sections 012200 and 334100)",
                "item_description_clean": "120-Inch Manhole",
                "specification": "012200",
                "alternate_specification": "334100",
                "pay_item_description": "Manhole",
                "supplemental_description": "120-Inch",
                "item": "012200 - Manhole",
                "item_code_raw": "",
                "item_code_norm": "",
                "section_code_raw": "012200",
                "section_code_norm": "012200",
                "unit_code_raw": "EA",
                "unit_code_norm": "EA",
                "quantity": 1,
                "bidder_name_raw": "BRAVO",
                "bidder_name_canonical": "BRAVO",
                "bidder_type": "CONTRACTOR",
                "is_engineers_estimate": False,
                "unit_price": 120.0,
                "total_price": 120.0,
                "price_valid_flag": True,
                "parse_confidence": 0.95,
                "is_totals_row": False,
            },
            {
                "extract_run_id": "r1",
                "source_file": "f.xlsx",
                "source_sheet": "Base Bid",
                "source_row_index": 13,
                "project_ean": "P1",
                "solicitation_no": "S1",
                "project_name_raw": "Proj",
                "letting_date": "2026-01-01",
                "location_name_raw": "PDX",
                "bid_schedule_name": "Base Bid",
                "bid_schedule_type": "BASE",
                "bid_schedule_code": "",
                "line_no": "",
                "item_description_raw": "Total Amount Bid",
                "item_description_clean": "Total Amount Bid",
                "specification": "",
                "alternate_specification": "",
                "pay_item_description": "",
                "supplemental_description": "",
                "item": "",
                "item_code_raw": "",
                "item_code_norm": "",
                "section_code_raw": "",
                "section_code_norm": "",
                "unit_code_raw": "",
                "unit_code_norm": "",
                "quantity": None,
                "bidder_name_raw": "ACME",
                "bidder_name_canonical": "ACME",
                "bidder_type": "CONTRACTOR",
                "is_engineers_estimate": False,
                "unit_price": None,
                "total_price": None,
                "price_valid_flag": False,
                "parse_confidence": 0.85,
                "is_totals_row": True,
            },
        ]
    )


def test_build_model_emits_fact_and_dims_from_in_memory_frames():
    clean_df = _sample_clean_df()
    config_tables = {
        "location_dictionary": pd.DataFrame([{"location_name_raw": "PDX", "location_code": "PDX"}]),
    }

    model = build_model(clean_df, config_tables)

    fact = model["fact"]
    assert set(["project_id", "scope_id", "bidder_id", "pay_item_id"]).issubset(fact.columns)
    assert len(fact) == 2
    assert fact["line_no"].astype(str).str.strip().ne("").all()
    assert set(fact["scope_type"]) == {"BASE", "ALT"}

    dims = [model["dim_project"], model["dim_scope"], model["dim_bidder"], model["dim_pay_item"]]
    assert all(not dim.empty for dim in dims)
