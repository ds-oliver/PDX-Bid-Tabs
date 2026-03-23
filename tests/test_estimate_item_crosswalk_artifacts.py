from pathlib import Path

import pandas as pd


DETAIL_PATH = Path("./reports/estimate_item_crosswalk_detail.csv")
TABLE_PATH = Path("./reports/estimate_item_crosswalk_table.csv")
UNMAPPED_PATH = Path("./reports/estimate_item_crosswalk_unmapped.csv")
OUT_SCOPE_PATH = Path("./reports/estimate_item_crosswalk_out_of_catalog_scope.csv")


def test_estimate_item_crosswalk_outputs_and_semantics():
    import subprocess
    import sys

    subprocess.check_call(
        [
            sys.executable,
            "scripts/build_estimate_item_crosswalk.py",
            "--input_csv",
            "./data_out/compiled_excel_itemized_clean.csv",
            "--catalog_xlsx",
            "./data_in/DRAFT One Port Estimating - Quantities Tool.xlsx",
            "--out_dir",
            "./reports",
            "--out_prefix",
            "estimate_item_crosswalk",
        ]
    )

    assert DETAIL_PATH.exists()
    assert TABLE_PATH.exists()
    assert UNMAPPED_PATH.exists()
    assert OUT_SCOPE_PATH.exists()
    detail = pd.read_csv(DETAIL_PATH, keep_default_na=False)
    table = pd.read_csv(TABLE_PATH, keep_default_na=False)
    unmapped = pd.read_csv(UNMAPPED_PATH, keep_default_na=False)
    out_scope = pd.read_csv(OUT_SCOPE_PATH, keep_default_na=False)

    required_detail = {
        "project_ean",
        "line_no",
        "item_description_raw",
        "estimate_item",
        "cost_code",
        "needs_slicer",
        "size_in",
        "material_or_type",
        "spec_family",
        "match_method",
        "match_confidence",
        "mapping_status",
        "needs_review",
    }
    assert required_detail.issubset(detail.columns)

    assert list(table.columns) == [
        "Estimate Item",
        "Bid Tab Count",
        "Project EAN",
        "Raw Bid Tab Item Description",
    ]

    # Bid Tab Count semantics: count unique project+line rows for each estimate-item + raw description.
    mapped = detail[detail["estimate_item"].astype(str).str.strip() != ""].copy()
    mapped["line_key"] = mapped["project_ean"].astype(str) + "|" + mapped["line_no"].astype(str)
    check = (
        mapped.groupby(["estimate_item", "item_description_raw"], dropna=False)["line_key"]
        .nunique()
        .reset_index(name="expected_count")
    )
    joined = table.merge(
        check,
        left_on=["Estimate Item", "Raw Bid Tab Item Description"],
        right_on=["estimate_item", "item_description_raw"],
        how="left",
    )
    assert (joined["Bid Tab Count"] == joined["expected_count"]).all()

    # Known mapping families should be present and mapped when source rows exist.
    def _assert_term_maps(term: str, expected_token: str) -> None:
        rows = detail[detail["item_description_raw"].astype(str).str.upper().str.contains(term, na=False)]
        if rows.empty:
            return
        mapped_rows = rows[rows["estimate_item"].astype(str).str.upper().str.contains(expected_token.upper(), na=False)]
        assert not mapped_rows.empty

    _assert_term_maps("ESCORT", "ESCORT")
    _assert_term_maps("TRAFFIC CONTROL", "TRAFFIC CONTROL")
    pavement_rows = detail[detail["item_description_raw"].astype(str).str.upper().str.contains("PAVEMENT", na=False)]
    if not pavement_rows.empty:
        mapped_items = set(pavement_rows["estimate_item"].astype(str))
        assert any(
            any(c in str(x).upper() for c in ["PCC PAVEMENT", "PCC PAVEMENT REMOVAL", "PORTLAND CEMENT"])
            for x in [
                *mapped_items
            ]
        )

    # Flagged slicer families should populate core slicer fields when mapped.
    slicer_rows = detail[
        detail["estimate_item"].isin(
            [
                "321300 Portland Cement Concrete Pavement",
                "550000 PCC Pavement (P-501)",
                "331116 Water Pipe",
                "334100 Stormwater Pipe",
                "333100 Sanitary Pipe",
                "328400 Irrigation Line",
            ]
        )
    ]
    if not slicer_rows.empty:
        flagged = slicer_rows[slicer_rows["needs_slicer"].astype(str).str.lower().isin(["true", "1"])]
        if not flagged.empty:
            assert (flagged["spec_family"].astype(str).str.strip() != "").any()

    # Numeric cost codes should always be six digits (left-padded when needed).
    mapped_codes = detail.loc[detail["estimate_item"].astype(str).str.strip() != "", "cost_code"].astype(str).str.strip()
    numeric_codes = mapped_codes[mapped_codes.str.fullmatch(r"\d+")]
    if not numeric_codes.empty:
        assert numeric_codes.str.fullmatch(r"\d{6}").all()

    # Unmapped output must only include unmapped rows.
    assert (unmapped["estimate_item"].astype(str).str.strip() == "").all()
    assert (unmapped["mapping_status"].astype(str) == "unmapped").all()

    # Out-of-catalog scope output must only include out_of_catalog_scope rows.
    assert (out_scope["estimate_item"].astype(str).str.strip() == "").all()
    assert (out_scope["mapping_status"].astype(str) == "out_of_catalog_scope").all()
