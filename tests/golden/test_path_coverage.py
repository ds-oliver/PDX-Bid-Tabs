"""Every config-driven rule in 02 and every quality path in 04 is exercised by a synthetic scenario.

Python coverage cannot see these: they are Spark SQL, or Python UDF code that
runs in Spark worker processes. Each test points at the evidence in the
reference snapshots. The refactored pipeline must reproduce the snapshots
exactly (test_refactored_equivalence.py), so the evidence holds for both.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"


def rows(scenario: str, rel: str) -> list[dict[str, str]]:
    text = (SNAPSHOTS / scenario / rel).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def stdout(scenario: str, notebook: str) -> str:
    return (SNAPSHOTS / scenario / "stdout" / f"{notebook}.txt").read_text(encoding="utf-8")


def display_with_columns(scenario: str, notebook: str, *columns: str) -> list[dict[str, str]]:
    matches = []
    for path in sorted((SNAPSHOTS / scenario / "displays" / notebook).glob("*.csv")):
        header = path.read_text(encoding="utf-8").split("\n", 1)[0].split(",")
        if all(c in header for c in columns):
            matches.append(path.relative_to(SNAPSHOTS / scenario).as_posix())
    assert len(matches) == 1, f"expected one display with {columns}, found {matches}"
    return rows(scenario, matches[0])


# --- 01 source paths --------------------------------------------------------


def test_skip_files_hit():
    assert "skipped_files=['PDX_2017D013.xlsx']" in stdout("base_run1", "01_parse_single_bidtab")
    bronze = rows("base_run1", "tables/bronze_raw_rows.csv")
    assert not [r for r in bronze if r["source_file"] == "PDX_2017D013.xlsx"]


def test_ref_rows_reach_bronze_and_are_dropped_in_silver():
    bronze = rows("base_run1", "tables/bronze_raw_rows.csv")
    silver = rows("base_run1", "tables/silver_bid_items.csv")
    assert [r for r in bronze if r["item_description_raw"] == "#REF!"]
    assert not [r for r in silver if r["item_description_raw"] == "#REF!"]
    # A #REF! price cell parses to null.
    beta_asphalt = [
        r
        for r in bronze
        if r["contractor_name"] == "Beta Builders LLC" and r["item_description_raw"].startswith("Asphalt")
    ]
    assert beta_asphalt and all(r["unit_price"] == "<null>" for r in beta_asphalt)


def test_alternate_only_workbook():
    bronze = [r for r in rows("base_run1", "tables/bronze_raw_rows.csv") if r["source_file"] == "SYN_D.xlsx"]
    assert bronze and {r["bid_type"] for r in bronze} == {"Alternate Bid Tab"}
    mart = [r for r in rows("base_run1", "tables/mart_bid_analysis.csv") if r["source_file"] == "SYN_D.xlsx"]
    assert mart and {r["tab_type"] for r in mart} == {"ALT"}


# --- 02 config-driven rules -------------------------------------------------


def _silver_normalized(raw: str) -> set[str]:
    silver = rows("base_run1", "tables/silver_bid_items.csv")
    return {r["item_description_normalized"] for r in silver if r["item_description_raw"] == raw}


def test_concat_fixes_applied():
    assert _silver_normalized("WORKZONE TRAFFICCONTROL") == {"WORK ZONE TRAFFIC CONTROL"}


def test_text_normalization_applied():
    assert _silver_normalized('Asphalt Pavement, 4" Thick') == {"ASPHALT PAVEMENT 4-INCH"}


def test_unit_mapping_loaded_but_not_applied():
    """unit_mapping.csv is loaded (a missing file fails the job) but no query reads it (backlog B-05)."""
    assert "Loaded 2 unit mappings from" in stdout("base_run1", "02_build_silver")
    silver = rows("base_run1", "tables/silver_bid_items.csv")
    # unit_mapping.csv maps 'Each' -> EA; Silver gets EA from its hard-coded CASE, and also maps
    # values the CSV does not list ('C.Y.' -> CY), which shows the CASE is what applies.
    assert {r["unit_clean"] for r in silver if r["unit"] == "C.Y."} == {"CY"}


def test_contractor_alias_collapse():
    silver = rows("base_run1", "tables/silver_bid_items.csv")
    variants = {r["contractor_name_clean"] for r in silver if r["awarded_bidder_canonical"] == "ACME PAVING INC"}
    assert variants == {"ACME PAVING, INC.", "ACME PAVING INC"}


def test_awarded_bid_join_hit_and_misses():
    silver = rows("base_run2", "tables/silver_bid_items.csv")
    by_file = {}
    for r in silver:
        by_file.setdefault(r["source_file"], set()).add((r["awarded_bidder_canonical"], r["is_awarded_bid"]))
    # Hit: the awarded bidder on a solicitation in the award list.
    assert ("ACME PAVING INC", "true") in by_file["SYN_A Bid Tab.xlsx"]
    # Miss: another bidder on the same solicitation, and a row with no award amount (Beta).
    assert ("BETA BUILDERS", "false") in by_file["SYN_A Bid Tab.xlsx"]
    # Miss: a solicitation that is not in the award list at all.
    assert {flag for _, flag in by_file["SYN_C.xlsx"]} == {"false"}


# --- 04 mart and quality paths ----------------------------------------------


def test_unit_price_backfill():
    mart = rows("base_run1", "tables/mart_bid_analysis.csv")
    backfilled = [r for r in mart if r["unit_price"] == "<null>" and r["effective_unit_price"] != "<null>"]
    assert backfilled


def test_price_suspicious_flag_true_for_a_contractor_in_default_mart():
    mart = rows("base_run1", "tables/mart_bid_analysis.csv")
    assert [r for r in mart if r["price_suspicious_flag"] == "true" and r["is_engineers_estimate"] == "false"]


def test_delta_report_shows_every_status():
    report = display_with_columns("base_run2", "04_build_mart", "status", "rows_now", "rows_prior")
    status = {r["source_file"]: r["status"] for r in report}
    assert status["SYN_A Bid Tab.xlsx"] == "✅ unchanged"
    assert status["SYN_B.xlsx"].startswith("❌ REMOVED")
    assert status["SYN_C.xlsx"].startswith("🆕 NEW")
    assert status["SYN_E.xlsx"].startswith("🔄 CHANGED — rows")
    assert status["SYN_F.xlsx"].startswith("🔄 CHANGED — bidders")
    assert status["SYN_G.xlsx"].startswith("🔄 AWARDED")
    assert status["SYN_H.xlsx"].startswith("🔄 UNMAPPED")


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [("base_run1", "✅ PASS (EE excluded as expected)"), ("ee_included", "✅ PASS (EE included)")],
)
def test_run_health_check_paths(scenario, expected):
    health = display_with_columns(scenario, "04_build_mart", "silver_to_mart_check")
    assert [r["silver_to_mart_check"] for r in health] == [expected]
