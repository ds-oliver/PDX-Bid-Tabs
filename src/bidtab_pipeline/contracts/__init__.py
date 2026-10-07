"""Table contracts: column names and Spark types, in order.

Derived from the 2026-05-28 reference notebooks (reference/databricks_2026-05-28/)
and checked against them by tests/contract/. Types are Spark `simpleString()`
values.

`mart_bid_analysis` is frozen (BRD FR-40): same columns, types, and grain. New
columns are additive only.
"""

from __future__ import annotations

Column = tuple[str, str]

# 01 writes with an explicit StructType, then adds bronze_loaded_at.
BRONZE_RAW_ROWS: tuple[Column, ...] = (
    ("source_file", "string"),
    ("source_sheet", "string"),
    ("bid_type", "string"),
    ("ean", "string"),
    ("project_name", "string"),
    ("airport_name", "string"),
    ("solicitation_no", "string"),
    ("bid_date", "date"),
    ("item_no", "string"),
    ("item_description_raw", "string"),
    ("estimated_quantity", "double"),
    ("unit", "string"),
    ("contractor_name", "string"),
    ("contractor_position", "int"),
    ("is_engineers_estimate", "boolean"),
    ("unit_price", "double"),
    ("total_price", "double"),
    ("is_section_header", "boolean"),
    ("bronze_loaded_at", "timestamp"),
)

# 02 CREATE OR REPLACE TABLE ... AS SELECT.
SILVER_BID_ITEMS: tuple[Column, ...] = (
    ("source_file", "string"),
    ("source_sheet", "string"),
    ("bid_type", "string"),
    ("tab_type", "string"),
    ("ean", "string"),
    ("project_name", "string"),
    ("airport_name", "string"),
    ("project_name_full", "string"),
    ("solicitation_no_raw", "string"),
    ("solicitation_no", "string"),
    ("bid_date", "date"),
    ("bid_year", "int"),
    ("item_no", "string"),
    ("item_no_sort", "double"),
    ("item_description_raw", "string"),
    ("item_description_clean", "string"),
    ("item_description_normalized", "string"),
    ("estimated_quantity", "double"),
    ("unit", "string"),
    ("unit_clean", "string"),
    ("contractor_name_clean", "string"),
    ("awarded_bidder_canonical", "string"),
    ("contractor_position", "int"),
    ("is_engineers_estimate", "boolean"),
    ("is_awarded_bid", "boolean"),
    ("unit_price", "double"),
    ("total_price", "double"),
    ("unit_price_null_flag", "boolean"),
    ("total_price_zero_flag", "boolean"),
    ("price_suspicious_flag", "boolean"),
    ("bronze_loaded_at", "timestamp"),
    ("silver_loaded_at", "timestamp"),
)

# 02 writes the de-duplicated awarded bids list from pandas.
REF_AWARDED_BIDS: tuple[Column, ...] = (
    ("invitation_no", "string"),
    ("awarded_bidder_canonical", "string"),
    ("award_amount", "double"),
)

# 03 writes the projected crosswalk from pandas (all columns read as str).
INT_CROSSWALK: tuple[Column, ...] = (
    ("item_description_raw", "string"),
    ("raw_join_key", "string"),
    ("item_description_normalized", "string"),
    ("catalog_cost_code_original", "string"),
    ("catalog_cost_code", "string"),
    ("catalog_cost_code_desc", "string"),
    ("catalog_division", "string"),
    ("faa_item_code", "string"),
    ("port_section_code", "string"),
    ("spec_type", "string"),
)

# 04 CREATE OR REPLACE TABLE ... AS SELECT. Frozen (FR-40).
MART_BID_ANALYSIS: tuple[Column, ...] = (
    ("bid_item_sk", "string"),
    ("natural_key", "string"),
    ("ean", "string"),
    ("project_name_full", "string"),
    ("project_name", "string"),
    ("airport_name", "string"),
    ("solicitation_no", "string"),
    ("bid_date", "date"),
    ("bid_year", "int"),
    ("source_file", "string"),
    ("bid_type", "string"),
    ("tab_type", "string"),
    ("item_no", "string"),
    ("item_no_sort", "double"),
    ("item_description_raw", "string"),
    ("item_description_normalized", "string"),
    ("item_description_standardized", "string"),
    ("catalog_item_description", "string"),
    ("estimated_quantity", "double"),
    ("unit", "string"),
    ("catalog_division", "string"),
    ("catalog_cost_code", "string"),
    ("catalog_cost_code_desc", "string"),
    ("catalog_cost_code_original", "string"),
    ("spec_type", "string"),
    ("crosswalk_confidence", "string"),
    ("faa_item_code", "string"),
    ("port_section_code", "string"),
    ("is_catalog_mapped", "boolean"),
    ("contractor_name_canonical", "string"),
    ("contractor_position", "int"),
    ("is_engineers_estimate", "boolean"),
    ("is_awarded_bid", "boolean"),
    ("unit_price", "double"),
    ("total_price", "double"),
    ("effective_unit_price", "double"),
    ("unit_price_null_flag", "boolean"),
    ("total_price_zero_flag", "boolean"),
    ("price_suspicious_flag", "boolean"),
    ("bronze_loaded_at", "timestamp"),
    ("silver_loaded_at", "timestamp"),
    ("mart_loaded_at", "timestamp"),
)

# Grain of mart_bid_analysis: project x bid tab section x pay item x contractor.
# 04 hashes exactly these Silver columns into bid_item_sk (FR-22).
MART_GRAIN = ("bid_type", "ean", "item_no", "contractor_name_canonical")

# 04 CREATE OR REPLACE VIEW over the mart.
CROSSWALK_UNMAPPED_ITEMS: tuple[Column, ...] = (
    ("item_description_raw", "string"),
    ("affected_row_count", "bigint"),
    ("affected_project_count", "bigint"),
    ("example_projects", "array<string>"),
    ("latest_bid_year", "int"),
    ("latest_bid_date", "date"),
    ("suggested_action", "string"),
    ("report_generated_at", "timestamp"),
)

# 04 append-only audit tables (CREATE TABLE IF NOT EXISTS, then INSERT).
PIPELINE_RUN_LOG: tuple[Column, ...] = (
    ("run_id", "string"),
    ("run_timestamp", "timestamp"),
    ("bronze_rows", "bigint"),
    ("silver_rows", "bigint"),
    ("crosswalk_rows", "bigint"),
    ("mart_rows", "bigint"),
    ("silver_to_mart_pass", "boolean"),
    ("catalog_mapped_pct", "double"),
    ("unmapped_count", "bigint"),
    ("projects_in_mart", "bigint"),
    ("projects_awarded", "bigint"),
    ("notes", "string"),
)

PIPELINE_FILE_LOG: tuple[Column, ...] = (
    ("run_id", "string"),
    ("run_timestamp", "timestamp"),
    ("source_file", "string"),
    ("ean", "string"),
    ("project_name", "string"),
    ("bid_date", "date"),
    ("mart_rows", "bigint"),
    ("bidder_count", "bigint"),
    ("item_count", "bigint"),
    ("awarded_bidder", "string"),
    ("awarded_total", "double"),
    ("unmapped_items", "bigint"),
)

XLSX_PATH_TABLES: dict[str, tuple[Column, ...]] = {
    "bronze_raw_rows": BRONZE_RAW_ROWS,
    "silver_bid_items": SILVER_BID_ITEMS,
    "ref_awarded_bids": REF_AWARDED_BIDS,
    "int_crosswalk": INT_CROSSWALK,
    "mart_bid_analysis": MART_BID_ANALYSIS,
    "crosswalk_unmapped_items": CROSSWALK_UNMAPPED_ITEMS,
    "pipeline_run_log": PIPELINE_RUN_LOG,
    "pipeline_file_log": PIPELINE_FILE_LOG,
}

# 05 writes these six to /Volumes/pop-poc/bidtab/exports/<name>.csv.
EXPORTED_TABLES = (
    "bronze_raw_rows",
    "silver_bid_items",
    "mart_bid_analysis",
    "ref_awarded_bids",
    "int_crosswalk",
    "crosswalk_unmapped_items",
)
