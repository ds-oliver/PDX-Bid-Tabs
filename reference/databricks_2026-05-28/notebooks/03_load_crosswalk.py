# Databricks notebook source
# Loads pay item crosswalk CSV into int_crosswalk Delta table.
# Full refresh (overwrite). Safe to re-run.

# COMMAND ----------

CROSSWALK_CSV_PATH = "/Volumes/pop-poc/bidtab/config/Final_Recommended_Line_Item_List.csv"
CROSSWALK_TABLE = "`pop-poc`.`bidtab`.`int_crosswalk`"
SILVER_TABLE = "`pop-poc`.`bidtab`.`silver_bid_items`"

# COMMAND ----------

import pandas as pd
import re

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

# === Final column projection (drop QA-only columns from the Delta table) ===
_crosswalk_out = crosswalk_df[[
    "item_description_raw",
    "raw_join_key",
    "item_description_normalized",
    "catalog_cost_code_original",
    "catalog_cost_code",
    "catalog_cost_code_desc",
    "catalog_division",
    "faa_item_code",
    "port_section_code",
    "spec_type",
]]

# Write to Delta
_crosswalk_spark = spark.createDataFrame(_crosswalk_out)
_crosswalk_spark.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(CROSSWALK_TABLE)

# === Summary print ===
print(f"Crosswalk table {CROSSWALK_TABLE} built with {_crosswalk_spark.count()} rows.\n")

print(f"  spec_type breakdown:")
print("    " + crosswalk_df["spec_type"].value_counts().to_string().replace("\n", "\n    "))

_repairs = (crosswalk_df["_repair_note"] != "").sum()
_anomalies = (crosswalk_df["_code_class"] == "ANOMALY").sum()
print(f"\n  catalog_cost_code auto-repair results:")
print(f"    Repaired:  {_repairs} rows (see Cell 2c for details)")
print(f"    Anomalies: {_anomalies} rows still don't match FAA or Port pattern (see Cell 2c)")
print(f"\n  Distinct catalog_division:        {crosswalk_df['catalog_division'].nunique()}")
print(f"  Distinct catalog_cost_code:       {crosswalk_df['catalog_cost_code'].nunique()}")
print(f"  Distinct catalog_cost_code_desc:  {crosswalk_df['catalog_cost_code_desc'].nunique()}")
print(f"  FAA codes populated:              {crosswalk_df['faa_item_code'].notna().sum()}")
print(f"  Port codes populated:             {crosswalk_df['port_section_code'].notna().sum()}")

# COMMAND ----------

# Cost code QA report — auto-repairs and remaining anomalies.
# Anything in the ANOMALY rows below will NOT classify into faa_item_code or
# port_section_code on the mart, which means Power BI filters by those columns
# will miss them. Fix the source CSV and rerun if needed.

_qa = crosswalk_df[
    (crosswalk_df["_repair_note"] != "") | (crosswalk_df["_code_class"] == "ANOMALY")
][[
    "item_description_raw",
    "catalog_cost_code_original",
    "catalog_cost_code",
    "_code_class",
    "_repair_note",
    "spec_type",
    "catalog_division",
]].rename(columns={
    "_code_class": "post_repair_classification",
    "_repair_note": "repair_action",
})

if len(_qa) == 0:
    print("✅ No cost code repairs or anomalies — all values cleanly match FAA or Port pattern.")
else:
    print(f"Cost code QA: {len(_qa)} rows with repairs or anomalies.\n")
    print("  repair_action = 'repaired' → auto-fixed (typically zero-padded). Verify result is correct.")
    print("  repair_action = 'trimmed'  → whitespace stripped.")
    print("  post_repair_classification = 'ANOMALY' → still doesn't match either pattern. Fix the source CSV.\n")
    display(spark.createDataFrame(_qa))

# Clean up QA-only columns from the in-memory DataFrame (Delta table already written without them)
crosswalk_df = crosswalk_df.drop(columns=["_repair_note", "_code_class"], errors="ignore")

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS total_rows FROM {CROSSWALK_TABLE}"))

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          spec_type,
          COUNT(*) AS row_count,
          COUNT(DISTINCT item_description_normalized) AS distinct_standards,
          COUNT(DISTINCT catalog_division) AS distinct_divisions,
          COUNT(DISTINCT catalog_cost_code) AS distinct_sections,
          COUNT(DISTINCT catalog_cost_code_desc) AS distinct_section_descs
        FROM {CROSSWALK_TABLE}
        GROUP BY spec_type
        ORDER BY row_count DESC
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          'silver_to_crosswalk_coverage' AS check_name,
          COUNT(*) AS total_silver_rows,
          SUM(CASE WHEN c.raw_join_key IS NOT NULL THEN 1 ELSE 0 END) AS matched_rows,
          SUM(CASE WHEN c.raw_join_key IS NULL THEN 1 ELSE 0 END) AS unmatched_rows,
          ROUND(
            SUM(CASE WHEN c.raw_join_key IS NOT NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*),
            1
          ) AS match_rate_pct,
          CASE
            WHEN SUM(CASE WHEN c.raw_join_key IS NULL THEN 1 ELSE 0 END) = 0 THEN 'PASS'
            ELSE 'FAIL — see cell 6 for unmatched descriptions'
          END AS status
        FROM {SILVER_TABLE} s
        LEFT JOIN {CROSSWALK_TABLE} c
          ON LOWER(TRIM(s.item_description_raw)) = c.raw_join_key
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          s.item_description_raw,
          s.item_description_normalized AS silver_cleaned_description,
          COUNT(*) AS row_count,
          COUNT(DISTINCT s.ean) AS project_count
        FROM {SILVER_TABLE} s
        LEFT JOIN {CROSSWALK_TABLE} c
          ON LOWER(TRIM(s.item_description_raw)) = c.raw_join_key
        WHERE c.raw_join_key IS NULL
        GROUP BY s.item_description_raw, s.item_description_normalized
        ORDER BY row_count DESC
        """
    )
)

# COMMAND ----------

# MAGIC %sql
# MAGIC DESCRIBE TABLE `pop-poc`.`bidtab`.`int_crosswalk`

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          s.ean,
          s.bid_year,
          s.item_no,
          s.item_description_raw,
          c.item_description_normalized,
          c.catalog_division,
          c.catalog_cost_code,
          c.catalog_cost_code_desc,
          c.faa_item_code,
          c.port_section_code,
          c.spec_type,
          s.awarded_bidder_canonical,
          s.unit_price,
          s.total_price,
          s.is_awarded_bid
        FROM {SILVER_TABLE} s
        LEFT JOIN {CROSSWALK_TABLE} c
          ON LOWER(TRIM(s.item_description_raw)) = c.raw_join_key
        WHERE c.spec_type IN ('FAA', 'PORT')
        ORDER BY s.ean, TRY_CAST(s.item_no AS INT), s.item_no
        LIMIT 50
        """
    )
)