"""Crosswalk config loader with the 03 guardrails: verbatim port of reference notebook 03.

The body of load_crosswalk is 03's load-and-repair code copied unchanged and
indented one level (enforced by tests/unit/test_verbatim_ports.py). It
hard-fails (AssertionError) on a missing column, a NULL raw or normalized
description, a duplicate join key, or an unrecognized spec_type. Gaps in these
guardrails are kept on purpose; see docs/backlog.md B-01 to B-03.
"""

from __future__ import annotations

import re

import pandas as pd

CROSSWALK_FILE = "Final_Recommended_Line_Item_List.csv"


def load_crosswalk(CROSSWALK_CSV_PATH: str) -> pd.DataFrame:  # noqa: N803 - name kept from 03
    """Load, check, and repair the crosswalk CSV. Returns 03's working DataFrame, QA columns included."""
    # Load the Final Recommended Line Item List (v2 schema).
    # Source columns: item_description_raw, item_description_normalized,
    # catalog_cost_code_original, catalog_cost_code, spec_type, catalog_division,
    # catalog_cost_code_desc
    crosswalk_df = pd.read_csv(CROSSWALK_CSV_PATH, dtype=str)

    # === HARD-FAIL QA: schema and integrity ===
    _required_cols = {
        "item_description_raw",
        "item_description_normalized",
        "catalog_cost_code_original",
        "catalog_cost_code",
        "spec_type",
        "catalog_division",
        "catalog_cost_code_desc",
    }
    _missing = _required_cols - set(crosswalk_df.columns)
    assert not _missing, f"Crosswalk source is missing required columns: {_missing}"
    assert crosswalk_df["item_description_raw"].notna().all(), "Crosswalk has NULL item_description_raw rows"
    assert crosswalk_df["item_description_normalized"].notna().all(), "Crosswalk has NULL item_description_normalized rows"

    # Build the case-insensitive join key (matches transformation in 04 mart join).
    crosswalk_df["raw_join_key"] = crosswalk_df["item_description_raw"].str.lower().str.strip()

    # Hard-fail on duplicate keys — would cause mart row explosion.
    _dupes = crosswalk_df[crosswalk_df["raw_join_key"].duplicated(keep=False)]
    assert len(_dupes) == 0, f"Duplicate raw_join_key found ({len(_dupes)} rows). Mart join would explode."

    # === Defensive cleanups ===
    # Backtick typo fix: '56 Miscell`aneous FAA' → '56 Miscellaneous FAA'
    crosswalk_df["catalog_division"] = crosswalk_df["catalog_division"].str.replace(
        "Miscell`aneous", "Miscellaneous", regex=False
    )

    # Fill NULL Division with the synthetic Uncategorized bucket.
    crosswalk_df["catalog_division"] = crosswalk_df["catalog_division"].fillna("99 Uncategorized / Not Listed")

    # Normalize spec_type to uppercase. The .xlsx dropdown enforces FAA / PORT / UNK,
    # but a manual edit that bypasses the dropdown can introduce mixed case. Forcing
    # uppercase here protects Power BI filters from silent misses.
    crosswalk_df["spec_type"] = crosswalk_df["spec_type"].str.upper().str.strip()

    # Hard-fail on unrecognized spec_type values.
    _allowed_spec_types = {"FAA", "PORT", "UNK"}
    _bad_spec_types = set(crosswalk_df["spec_type"].dropna().unique()) - _allowed_spec_types
    assert not _bad_spec_types, (
        f"Unrecognized spec_type values: {_bad_spec_types}. "
        f"Allowed: {_allowed_spec_types}. Fix the source CSV and rerun."
    )

    # === Auto-repair catalog_cost_code ===
    # Common Excel artifacts:
    #   - Leading zeros stripped on Port section codes (e.g., '24113' should be '024113')
    #   - Stray whitespace
    #   - Mixed-case FAA codes (e.g., 'p-152' should be 'P-152')
    #
    # Auto-repair what's mechanically unambiguous; surface anything else in Cell 2c.
    _FAA_PAT = re.compile(r"^[A-Z]{1,2}-\d{2,4}$", re.I)
    _PORT_PAT = re.compile(r"^\d{6}$")

    def _repair_cost_code(s):
        """Returns (repaired_value, repair_note) tuple. repair_note is empty if no change."""
        if not isinstance(s, str) or s.strip() == "" or s.strip().lower() == "nan":
            return None, ""
        original = s
        s = s.strip()
        # Zero-pad 1-5 digit numeric values to 6 digits (Excel-stripped-zero fix)
        if s.isdigit() and 1 <= len(s) <= 5:
            s = s.zfill(6)
        # Normalize FAA codes to uppercase
        if _FAA_PAT.match(s):
            s = s.upper()
        return s, ("repaired" if s != original.strip() else ("trimmed" if s != original else ""))

    _repair_results = crosswalk_df["catalog_cost_code"].apply(_repair_cost_code)
    crosswalk_df["catalog_cost_code"] = _repair_results.apply(lambda x: x[0])
    crosswalk_df["_repair_note"] = _repair_results.apply(lambda x: x[1])

    # === Classify remaining anomalies (for surfacing in Cell 2c) ===
    def _classify(s):
        if not isinstance(s, str):
            return "NULL"
        if _FAA_PAT.match(s):
            return "FAA"
        if _PORT_PAT.match(s):
            return "PORT"
        return "ANOMALY"

    crosswalk_df["_code_class"] = crosswalk_df["catalog_cost_code"].apply(_classify)

    # === Split catalog_cost_code into faa_item_code + port_section_code ===
    def _faa(s):
        return s.strip().upper() if isinstance(s, str) and _FAA_PAT.match(s.strip()) else None

    def _port(s):
        return s.strip() if isinstance(s, str) and _PORT_PAT.match(s.strip()) else None

    crosswalk_df["faa_item_code"] = crosswalk_df["catalog_cost_code"].apply(_faa)
    crosswalk_df["port_section_code"] = crosswalk_df["catalog_cost_code"].apply(_port)

    return crosswalk_df
