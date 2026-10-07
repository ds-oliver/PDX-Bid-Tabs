"""Contracts derived from the 2026-05-28 baseline, checked against the reference notebooks.

Phase 2 points these same tests at the refactored package. Anything that
passes here and fails there is a behavior change.

Live-table checks use base_run2 (SYN_A and SYN_C, after a prior run) and
ee_included. base_run1 shares its database with base_run2, so only its
captured files are used.
"""

from __future__ import annotations

import csv
import io

import pytest
from pyspark.sql import functions as F

from bidtab_pipeline.contracts import (
    EXPORTED_TABLES,
    MART_BID_ANALYSIS,
    MART_GRAIN,
    XLSX_PATH_TABLES,
)

pytestmark = pytest.mark.spark


def _schema(df):
    return tuple((f.name, f.dataType.simpleString()) for f in df.schema.fields)


@pytest.mark.parametrize("table", sorted(XLSX_PATH_TABLES))
def test_table_columns_and_types(table, reference_outputs):
    scenario = reference_outputs["base_run2"]
    assert _schema(scenario.live_table(table)) == XLSX_PATH_TABLES[table]


def test_ee_toggle_does_not_change_mart_schema(reference_outputs):
    """FR-40: the mart contract holds with INCLUDE_ENG_EST either way."""
    scenario = reference_outputs["ee_included"]
    assert _schema(scenario.live_table("mart_bid_analysis")) == MART_BID_ANALYSIS


def test_exports_are_the_six_tables(reference_outputs):
    exports = reference_outputs["base_run2"].harness.volumes_root / "exports"
    assert sorted(p.stem for p in exports.glob("*.csv")) == sorted(EXPORTED_TABLES)


# --- mart grain (FR-22, FR-40) ----------------------------------------------


def test_mart_grain_is_unique(reference_outputs):
    mart = reference_outputs["base_run2"].live_table("mart_bid_analysis")
    assert mart.count() == mart.select(*MART_GRAIN).distinct().count()
    assert mart.count() == mart.select("bid_item_sk").distinct().count()


def test_surrogate_keys_are_deterministic_hashes_of_the_grain(reference_outputs):
    mart = reference_outputs["base_run2"].live_table("mart_bid_analysis")
    expected_sk = F.sha2(F.concat_ws("~", *[F.col(c) for c in MART_GRAIN]), 256)
    expected_nk = F.concat_ws("~", "bid_type", "ean", "item_no")
    mismatched = mart.where((F.col("bid_item_sk") != expected_sk) | (F.col("natural_key") != expected_nk))
    assert mismatched.count() == 0


def test_surrogate_keys_are_stable_across_runs(reference_outputs):
    """SYN_A is in both runs; its keys must not change."""
    keys = []
    for scenario in ("base_run1", "base_run2"):
        text = reference_outputs[scenario].files["tables/mart_bid_analysis.csv"]
        rows = csv.DictReader(io.StringIO(text))
        keys.append(sorted(r["bid_item_sk"] for r in rows if r["source_file"] == "SYN_A Bid Tab.xlsx"))
    assert keys[0] and keys[0] == keys[1]


# --- Engineer's Estimate at each layer (FR-15, FR-41) -----------------------


def _ee_count(df):
    return df.where(F.col("is_engineers_estimate")).count()


def test_bronze_keeps_and_flags_ee_rows(reference_outputs):
    bronze = reference_outputs["base_run2"].live_table("bronze_raw_rows")
    flagged = bronze.where(F.col("is_engineers_estimate")).select("contractor_name").distinct().collect()
    # 01 flags any bidder label containing both "engineer" and "estimate".
    assert sorted(r[0] for r in flagged) == ["Engineer's Estimate", "Engineers Estimate"]
    assert bronze.where(F.col("is_engineers_estimate").isNull()).count() == 0


def test_silver_passes_ee_rows_through(reference_outputs):
    scenario = reference_outputs["base_run2"]
    bronze = scenario.live_table("bronze_raw_rows")
    silver = scenario.live_table("silver_bid_items")
    # Silver drops '#REF!' and '0' descriptions for every bidder, EE included.
    dropped = F.col("item_description_raw").isin("#REF!") | (F.trim("item_description_raw") == "0")
    assert _ee_count(silver) == _ee_count(bronze.where(~dropped)) > 0


def test_mart_excludes_ee_rows_by_default(reference_outputs):
    scenario = reference_outputs["base_run2"]
    silver = scenario.live_table("silver_bid_items")
    mart = scenario.live_table("mart_bid_analysis")
    assert _ee_count(mart) == 0
    assert mart.count() == silver.where(~F.col("is_engineers_estimate")).count()


def test_mart_keeps_ee_rows_when_toggle_on(reference_outputs):
    scenario = reference_outputs["ee_included"]
    silver = scenario.live_table("silver_bid_items")
    mart = scenario.live_table("mart_bid_analysis")
    assert mart.count() == silver.count()
    assert _ee_count(mart) == _ee_count(silver) > 0
