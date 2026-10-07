# Databricks notebook source
# Gold mart table for bidtab pipeline.
# Joins silver_bid_items + int_crosswalk into mart_bid_analysis.
# This is the single table Power BI connects to.
# Full refresh (CREATE OR REPLACE TABLE). Safe to re-run.

# COMMAND ----------

SILVER_TABLE = "`pop-poc`.`bidtab`.`silver_bid_items`"
CROSSWALK_TABLE = "`pop-poc`.`bidtab`.`int_crosswalk`"
MART_TABLE = "`pop-poc`.`bidtab`.`mart_bid_analysis`"

# Toggle: include Engineer's Estimate rows in the mart.
# Default is False so the mart contains only true contractor bids — matches the
# expectation of existing Power BI measures and avoids skewing contractor averages.
# Flip to True when an analyst wants EE data available for variance/baseline analysis.
# Bronze and Silver always retain EE rows; this only controls what reaches the mart.
INCLUDE_ENG_EST = False

# COMMAND ----------

# Build the EE filter clause based on the toggle.
# When False (default): exclude EE rows from the mart. Power BI sees only contractor bids.
# When True: keep EE rows. Downstream visuals should filter on is_engineers_estimate as needed.
ee_filter_clause = "" if INCLUDE_ENG_EST else "WHERE NOT s.is_engineers_estimate"

spark.sql(
    f"""
    CREATE OR REPLACE TABLE {MART_TABLE} AS
    SELECT
      SHA2(CONCAT_WS('~', s.bid_type, s.ean, s.item_no, s.awarded_bidder_canonical), 256) AS bid_item_sk,
      CONCAT_WS('~', s.bid_type, s.ean, s.item_no) AS natural_key,

      s.ean, s.project_name_full, s.project_name, s.airport_name,
      s.solicitation_no, s.bid_date, s.bid_year,

      s.source_file, s.bid_type, s.tab_type,

      s.item_no, s.item_no_sort,

      -- Three-layer description hierarchy:
      --   raw         = verbatim from the bid tab
      --   normalized  = silver's lightly-cleaned version (spacing, capitalization, punctuation)
      --   standardized = Jennifer Scott's deeply-standardized name from the catalog crosswalk
      s.item_description_raw,
      s.item_description_normalized,

      CASE
        WHEN c.raw_join_key IS NULL
          THEN '⚠️ Unmapped — see crosswalk_unmapped_items'
        ELSE c.item_description_normalized
      END AS item_description_standardized,

      -- Legacy alias of item_description_standardized for BI dashboard compatibility.
      -- Kim's existing Power BI measures reference this name.
      CASE
        WHEN c.raw_join_key IS NULL
          THEN '⚠️ Unmapped — see crosswalk_unmapped_items'
        ELSE c.item_description_normalized
      END AS catalog_item_description,

      s.estimated_quantity,
      s.unit_clean AS unit,

      -- Catalog mapping fields from Jennifer Scott's Final Recommended Line Item List.
      -- Unmapped rows (LEFT JOIN miss) get '100 - Unmapped' / 'UNMAPPED' fallback labels
      -- so dashboards stay navigable. See crosswalk_unmapped_items view for resolution list.
      CASE
        WHEN c.raw_join_key IS NULL THEN '100 - Unmapped'
        ELSE c.catalog_division
      END AS catalog_division,

      CASE
        WHEN c.raw_join_key IS NULL THEN 'UNMAPPED'
        ELSE c.catalog_cost_code
      END AS catalog_cost_code,

      c.catalog_cost_code_desc,
      c.catalog_cost_code_original,

      CASE
        WHEN c.raw_join_key IS NULL THEN 'UNMAPPED'
        ELSE c.spec_type
      END AS spec_type,

      -- Deprecated field (no source data in current crosswalk). Retained as NULL
      -- column for backward compatibility with existing BI references.
      CAST(NULL AS STRING) AS crosswalk_confidence,

      c.faa_item_code,
      c.port_section_code,

      CASE
        WHEN c.raw_join_key IS NOT NULL THEN TRUE
        ELSE FALSE
      END AS is_catalog_mapped,

      s.awarded_bidder_canonical AS contractor_name_canonical,
      s.contractor_position,
      s.is_engineers_estimate,
      s.is_awarded_bid,

      s.unit_price, s.total_price,

      CASE
        WHEN s.estimated_quantity IS NOT NULL
             AND s.estimated_quantity > 0
             AND s.total_price IS NOT NULL
          THEN ROUND(s.total_price / s.estimated_quantity, 2)
        ELSE NULL
      END AS effective_unit_price,

      s.unit_price_null_flag, s.total_price_zero_flag, s.price_suspicious_flag,

      s.bronze_loaded_at,
      s.silver_loaded_at,
      current_timestamp() AS mart_loaded_at

    FROM {SILVER_TABLE} s
    LEFT JOIN {CROSSWALK_TABLE} c
      ON LOWER(TRIM(s.item_description_raw)) = c.raw_join_key
    {ee_filter_clause}
    """
)
print(f"Mart table {MART_TABLE} built successfully.")
print(f"  INCLUDE_ENG_EST = {INCLUDE_ENG_EST}")
print(f"  Engineer's Estimate rows {'INCLUDED' if INCLUDE_ENG_EST else 'EXCLUDED'} from this mart build.")

# COMMAND ----------

# Verify the INCLUDE_ENG_EST toggle behavior
ee_check = spark.sql(f"""
    SELECT
      COUNT(*) AS total_mart_rows,
      SUM(CASE WHEN is_engineers_estimate THEN 1 ELSE 0 END) AS ee_rows,
      SUM(CASE WHEN NOT is_engineers_estimate THEN 1 ELSE 0 END) AS contractor_rows,
      CASE
        WHEN {str(INCLUDE_ENG_EST).lower()}
             AND SUM(CASE WHEN is_engineers_estimate THEN 1 ELSE 0 END) = 0
          THEN '⚠️ INCLUDE_ENG_EST=True but no EE rows present — check Bronze/Silver'
        WHEN NOT {str(INCLUDE_ENG_EST).lower()}
             AND SUM(CASE WHEN is_engineers_estimate THEN 1 ELSE 0 END) > 0
          THEN '⚠️ INCLUDE_ENG_EST=False but EE rows present — filter failed'
        ELSE '✅ EE toggle behavior matches expectation'
      END AS status
    FROM {MART_TABLE}
""")
display(ee_check)

# COMMAND ----------

UNMAPPED_VIEW = "`pop-poc`.`bidtab`.`crosswalk_unmapped_items`"

spark.sql(
    f"""
    CREATE OR REPLACE VIEW {UNMAPPED_VIEW} AS
    SELECT
      item_description_raw,
      COUNT(*) AS affected_row_count,
      COUNT(DISTINCT ean) AS affected_project_count,
      COLLECT_SET(ean) AS example_projects,
      MAX(bid_year) AS latest_bid_year,
      MAX(bid_date) AS latest_bid_date,
      'Add row to Final_Recommended_Line_Item_List.csv with: item_description_raw, item_description_normalized, catalog_cost_code_original, catalog_cost_code, spec_type, catalog_division, catalog_cost_code_desc. Re-upload to /Volumes/pop-poc/bidtab/config/ then rerun notebooks 03 and 04.' AS suggested_action,
      current_timestamp() AS report_generated_at
    FROM {MART_TABLE}
    WHERE NOT is_catalog_mapped
    GROUP BY item_description_raw
    ORDER BY affected_row_count DESC, affected_project_count DESC
    """
)
print(f"Unmapped resolution view {UNMAPPED_VIEW} built successfully.")

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          item_description_raw,
          affected_row_count,
          affected_project_count,
          example_projects,
          latest_bid_year,
          latest_bid_date
        FROM {UNMAPPED_VIEW}
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          'mart_vs_silver' AS check_name,
          s.silver_rows,
          m.mart_rows,
          CASE WHEN s.silver_rows = m.mart_rows THEN 'PASS' ELSE 'FAIL' END AS status
        FROM
          (SELECT COUNT(*) AS silver_rows FROM {SILVER_TABLE}) s,
          (SELECT COUNT(*) AS mart_rows FROM {MART_TABLE}) m
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) AS catalog_mapped_rows,

          -- Unmapped: raw description not found in Jennifer's file at all
          SUM(CASE WHEN NOT is_catalog_mapped THEN 1 ELSE 0 END) AS unmapped_rows,
          SUM(CASE WHEN catalog_division = '100 - Unmapped' THEN 1 ELSE 0 END) AS unmapped_division_rows,

          -- Uncategorized: in Jennifer's file but Division was left blank
          SUM(CASE WHEN catalog_division = '99 Uncategorized / Not Listed' THEN 1 ELSE 0 END) AS uncategorized_division_rows,
          SUM(CASE WHEN spec_type = 'UNK' THEN 1 ELSE 0 END) AS unk_spec_type_rows,

          ROUND(SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS mapped_pct,

          -- Three-layer description cardinality (raw → cleaned → standardized)
          COUNT(DISTINCT item_description_raw) AS distinct_raw,
          COUNT(DISTINCT item_description_normalized) AS distinct_normalized,
          COUNT(DISTINCT item_description_standardized) AS distinct_standardized,

          COUNT(DISTINCT catalog_division) AS distinct_divisions,
          COUNT(DISTINCT catalog_cost_code) AS distinct_sections,
          COUNT(DISTINCT catalog_cost_code_desc) AS distinct_section_descs
        FROM {MART_TABLE}
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          ean,
          project_name_full,
          bid_year,
          COUNT(DISTINCT contractor_name_canonical) AS total_bidders,
          MAX(CASE WHEN is_awarded_bid THEN contractor_name_canonical END) AS awarded_contractor,
          SUM(CASE WHEN is_awarded_bid THEN total_price ELSE 0 END) AS awarded_total_value,
          COUNT(DISTINCT item_no) AS item_count
        FROM {MART_TABLE}
        WHERE tab_type = 'BASE'
        GROUP BY ean, project_name_full, bid_year
        ORDER BY bid_year, ean
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          item_description_standardized,
          catalog_division,
          catalog_cost_code,
          catalog_cost_code_desc,
          spec_type,
          COUNT(*) AS row_count,
          COUNT(DISTINCT ean) AS project_count,
          ROUND(AVG(unit_price), 2) AS avg_unit_price,
          ROUND(MIN(unit_price), 2) AS min_unit_price,
          ROUND(MAX(unit_price), 2) AS max_unit_price,
          ROUND(AVG(total_price), 2) AS avg_total_price
        FROM {MART_TABLE}
        WHERE is_catalog_mapped
          AND unit_price IS NOT NULL
          AND unit_price > 0
        GROUP BY item_description_standardized, catalog_division, catalog_cost_code, catalog_cost_code_desc, spec_type
        ORDER BY project_count DESC, row_count DESC
        LIMIT 25
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          bid_year,
          item_description_standardized,
          COUNT(DISTINCT ean) AS projects,
          ROUND(AVG(unit_price), 2) AS avg_unit_price,
          ROUND(AVG(total_price), 2) AS avg_total_price,
          ROUND(AVG(CASE WHEN is_awarded_bid THEN total_price END), 2) AS avg_awarded_price
        FROM {MART_TABLE}
        WHERE item_description_standardized LIKE '%Mobilization%'
          AND tab_type = 'BASE'
          AND total_price IS NOT NULL
          AND total_price > 0
        GROUP BY bid_year, item_description_standardized
        ORDER BY bid_year, item_description_standardized
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN unit_price_null_flag THEN 1 ELSE 0 END) AS null_unit_price,
          SUM(CASE WHEN total_price_zero_flag THEN 1 ELSE 0 END) AS zero_total_price,
          SUM(CASE WHEN price_suspicious_flag THEN 1 ELSE 0 END) AS suspicious_price,
          SUM(CASE WHEN NOT is_catalog_mapped THEN 1 ELSE 0 END) AS not_catalog_mapped,
          ROUND(SUM(CASE WHEN unit_price IS NOT NULL AND unit_price > 0 AND is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS clean_and_mapped_pct
        FROM {MART_TABLE}
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT *
        FROM {MART_TABLE}
        WHERE is_catalog_mapped
          AND is_awarded_bid
        ORDER BY ean, item_no_sort
        LIMIT 30
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          item_description_raw,
          COUNT(*) AS row_count,
          COUNT(DISTINCT ean) AS project_count,
          COLLECT_SET(catalog_division) AS catalog_divisions,
          COLLECT_SET(spec_type) AS spec_types
        FROM {MART_TABLE}
        WHERE NOT is_catalog_mapped
        GROUP BY item_description_raw
        ORDER BY row_count DESC
        """
    )
)

# COMMAND ----------

# MAGIC %sql
# MAGIC -- 1. spec_type fan-out at mart grain
# MAGIC SELECT spec_type, COUNT(*) AS row_count, COUNT(DISTINCT ean) AS projects
# MAGIC FROM `pop-poc`.`bidtab`.`mart_bid_analysis`
# MAGIC GROUP BY spec_type ORDER BY spec_type;
# MAGIC

# COMMAND ----------

# MAGIC %sql
# MAGIC -- 2. Airport normalization (Silver)
# MAGIC SELECT airport_name, COUNT(DISTINCT ean) AS projects, COUNT(*) AS rows
# MAGIC FROM `pop-poc`.`bidtab`.`silver_bid_items`
# MAGIC GROUP BY airport_name ORDER BY airport_name;
# MAGIC

# COMMAND ----------

# MAGIC %sql
# MAGIC
# MAGIC -- 3. Hyphenated item_no audit
# MAGIC SELECT source_file, COUNT(*) AS total, SUM(CASE WHEN item_no_sort IS NULL THEN 1 ELSE 0 END) AS null_sort
# MAGIC FROM `pop-poc`.`bidtab`.`silver_bid_items`
# MAGIC GROUP BY source_file HAVING null_sort > 0;
# MAGIC

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT DISTINCT item_no, item_no_sort
# MAGIC FROM `pop-poc`.`bidtab`.`silver_bid_items`
# MAGIC WHERE source_file = 'PDX_2021D007 Bid Tab.xlsx'
# MAGIC ORDER BY item_no;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- 4. effective_unit_price sanity — 15 null unit prices should have backfill
# MAGIC SELECT
# MAGIC   SUM(CASE WHEN unit_price_null_flag THEN 1 ELSE 0 END) AS null_unit_price_rows,
# MAGIC   SUM(CASE WHEN unit_price_null_flag AND effective_unit_price IS NOT NULL THEN 1 ELSE 0 END) AS backfilled,
# MAGIC   SUM(CASE WHEN unit_price_null_flag AND effective_unit_price IS NULL THEN 1 ELSE 0 END) AS still_null
# MAGIC FROM `pop-poc`.`bidtab`.`mart_bid_analysis`;

# COMMAND ----------

# === RUN HEALTH SUMMARY ===
# Single-pane post-run check. Read this after every pipeline run to confirm:
#   1. All four layers produced rows
#   2. Silver → Mart join is consistent (accounting for the INCLUDE_ENG_EST toggle)
#   3. Catalog coverage is acceptable
#   4. No unmapped items waiting for crosswalk updates
#   5. Projects landed as expected
#
# The silver_to_mart_check is EE-toggle-aware:
#   - When INCLUDE_ENG_EST = False (default): mart should equal silver's non-EE row count
#   - When INCLUDE_ENG_EST = True:            mart should equal silver's total row count

display(spark.sql(f"""
    WITH layer_counts AS (
      SELECT
        (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`bronze_raw_rows`)            AS bronze_rows,
        (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`silver_bid_items`)           AS silver_rows,
        (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`silver_bid_items`
         WHERE NOT is_engineers_estimate)                                     AS silver_contractor_rows,
        (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`int_crosswalk`)              AS crosswalk_rows,
        (SELECT COUNT(*) FROM {MART_TABLE})                                    AS mart_rows,
        (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`crosswalk_unmapped_items`)   AS unmapped_descriptions
    ),
    coverage AS (
      SELECT
        ROUND(SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS mapped_pct,
        COUNT(DISTINCT ean) AS projects_in_mart,
        COUNT(DISTINCT CASE WHEN is_awarded_bid THEN ean END) AS projects_with_awarded,
        MAX(mart_loaded_at) AS last_mart_build
      FROM {MART_TABLE}
    )
    SELECT
      lc.bronze_rows,
      lc.silver_rows,
      lc.silver_contractor_rows,
      lc.crosswalk_rows,
      lc.mart_rows,
      CASE
        WHEN {str(INCLUDE_ENG_EST).lower()} AND lc.silver_rows = lc.mart_rows
          THEN '✅ PASS (EE included)'
        WHEN NOT {str(INCLUDE_ENG_EST).lower()} AND lc.silver_contractor_rows = lc.mart_rows
          THEN '✅ PASS (EE excluded as expected)'
        ELSE '❌ FAIL — silver-to-mart row count mismatch'
      END AS silver_to_mart_check,
      cv.mapped_pct AS catalog_mapped_pct,
      lc.unmapped_descriptions,
      cv.projects_in_mart,
      cv.projects_with_awarded,
      cv.last_mart_build
    FROM layer_counts lc, coverage cv
"""))

# COMMAND ----------

# === RUN-OVER-RUN AUDIT LOG ===
# Append-only history tables. One row per run summarizes pipeline health;
# one row per (run, file) captures per-source-file detail used by the delta cell below.
# Both tables are created on first run; appended thereafter.

# --- Table 1: run-level audit log ---
spark.sql("""
    CREATE TABLE IF NOT EXISTS `pop-poc`.`bidtab`.`pipeline_run_log` (
        run_id              STRING,
        run_timestamp       TIMESTAMP,
        bronze_rows         BIGINT,
        silver_rows         BIGINT,
        crosswalk_rows      BIGINT,
        mart_rows           BIGINT,
        silver_to_mart_pass BOOLEAN,
        catalog_mapped_pct  DOUBLE,
        unmapped_count      BIGINT,
        projects_in_mart    BIGINT,
        projects_awarded    BIGINT,
        notes               STRING
    ) USING DELTA
""")

# --- Table 2: per-file audit log ---
spark.sql("""
    CREATE TABLE IF NOT EXISTS `pop-poc`.`bidtab`.`pipeline_file_log` (
        run_id              STRING,
        run_timestamp       TIMESTAMP,
        source_file         STRING,
        ean                 STRING,
        project_name        STRING,
        bid_date            DATE,
        mart_rows           BIGINT,
        bidder_count        BIGINT,
        item_count          BIGINT,
        awarded_bidder      STRING,
        awarded_total       DOUBLE,
        unmapped_items      BIGINT
    ) USING DELTA
""")

# Generate one run_id for this entire run (used in both tables for correlation)
import uuid
run_id = str(uuid.uuid4())[:8]

# --- Insert the run-level summary row ---
# EE-toggle-aware silver_to_mart_pass: when INCLUDE_ENG_EST=False, the mart should
# equal Silver's non-EE row count; when True, mart should equal Silver total.
spark.sql(f"""
    INSERT INTO `pop-poc`.`bidtab`.`pipeline_run_log`
    SELECT
      '{run_id}' AS run_id,
      current_timestamp() AS run_timestamp,
      (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`bronze_raw_rows`),
      (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`silver_bid_items`),
      (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`int_crosswalk`),
      (SELECT COUNT(*) FROM {MART_TABLE}),
      CASE
        WHEN {str(INCLUDE_ENG_EST).lower()}
          THEN (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`silver_bid_items`) =
               (SELECT COUNT(*) FROM {MART_TABLE})
        ELSE (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`silver_bid_items` WHERE NOT is_engineers_estimate) =
             (SELECT COUNT(*) FROM {MART_TABLE})
      END AS silver_to_mart_pass,
      (SELECT ROUND(SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1)
       FROM {MART_TABLE}),
      (SELECT COUNT(*) FROM `pop-poc`.`bidtab`.`crosswalk_unmapped_items`),
      (SELECT COUNT(DISTINCT ean) FROM {MART_TABLE}),
      (SELECT COUNT(DISTINCT CASE WHEN is_awarded_bid THEN ean END) FROM {MART_TABLE}),
      NULL  -- notes — manual annotation field for unusual runs
""")

# --- Insert the per-file detail rows ---
# One row per source workbook currently in the mart, with project metadata and quality flags.
spark.sql(f"""
    INSERT INTO `pop-poc`.`bidtab`.`pipeline_file_log`
    SELECT
      '{run_id}' AS run_id,
      current_timestamp() AS run_timestamp,
      source_file,
      ean,
      MAX(project_name) AS project_name,
      MAX(bid_date) AS bid_date,
      COUNT(*) AS mart_rows,
      COUNT(DISTINCT contractor_name_canonical) AS bidder_count,
      COUNT(DISTINCT item_no) AS item_count,
      MAX(CASE WHEN is_awarded_bid THEN contractor_name_canonical END) AS awarded_bidder,
      SUM(CASE WHEN is_awarded_bid AND tab_type = 'BASE' THEN total_price ELSE 0 END) AS awarded_total,
      SUM(CASE WHEN NOT is_catalog_mapped THEN 1 ELSE 0 END) AS unmapped_items
    FROM {MART_TABLE}
    GROUP BY source_file, ean
""")

print(f"Logged run {run_id}")
print(f"  → pipeline_run_log:  1 row (run summary)")
print(f"  → pipeline_file_log: N rows (one per source file)")

# --- Display the last 10 runs ---
display(spark.sql("""
    SELECT * FROM `pop-poc`.`bidtab`.`pipeline_run_log`
    ORDER BY run_timestamp DESC LIMIT 10
"""))

# COMMAND ----------

# === POST-RUN DELTA REPORT ===
# Compares this run's files to the previous run's files.
# Surfaces: new files ingested, files removed, and any meaningful changes (rows, bidders, awarded contractor, unmapped counts).
# This is the first thing to read after a pipeline run to confirm any intended changes landed
# and that nothing else changed unexpectedly.

display(spark.sql("""
    WITH this_run AS (
      SELECT * FROM `pop-poc`.`bidtab`.`pipeline_file_log`
      WHERE run_id = (
        SELECT run_id FROM `pop-poc`.`bidtab`.`pipeline_file_log`
        ORDER BY run_timestamp DESC LIMIT 1
      )
    ),
    prev_run AS (
      SELECT * FROM `pop-poc`.`bidtab`.`pipeline_file_log`
      WHERE run_id = (
        SELECT run_id FROM `pop-poc`.`bidtab`.`pipeline_file_log`
        WHERE run_timestamp < (SELECT MAX(run_timestamp) FROM `pop-poc`.`bidtab`.`pipeline_file_log`)
        ORDER BY run_timestamp DESC LIMIT 1
      )
    )
    SELECT
      COALESCE(t.source_file, p.source_file) AS source_file,
      COALESCE(t.ean, p.ean) AS ean,
      COALESCE(t.project_name, p.project_name) AS project_name,
      CASE
        WHEN p.source_file IS NULL THEN '🆕 NEW — first time in pipeline'
        WHEN t.source_file IS NULL THEN '❌ REMOVED — was in prior run, not in this run'
        WHEN t.mart_rows != p.mart_rows
          THEN CONCAT('🔄 CHANGED — rows ', CAST(p.mart_rows AS STRING), ' → ', CAST(t.mart_rows AS STRING))
        WHEN t.bidder_count != p.bidder_count
          THEN CONCAT('🔄 CHANGED — bidders ', CAST(p.bidder_count AS STRING), ' → ', CAST(t.bidder_count AS STRING))
        WHEN t.awarded_bidder IS DISTINCT FROM p.awarded_bidder
          THEN CONCAT('🔄 AWARDED — ', COALESCE(p.awarded_bidder, '(none)'), ' → ', COALESCE(t.awarded_bidder, '(none)'))
        WHEN t.unmapped_items != p.unmapped_items
          THEN CONCAT('🔄 UNMAPPED ', CAST(p.unmapped_items AS STRING), ' → ', CAST(t.unmapped_items AS STRING))
        ELSE '✅ unchanged'
      END AS status,
      t.mart_rows AS rows_now,
      p.mart_rows AS rows_prior,
      t.awarded_bidder AS awarded_now,
      t.unmapped_items AS unmapped_now
    FROM this_run t
    FULL OUTER JOIN prev_run p USING (source_file)
    ORDER BY
      CASE
        WHEN p.source_file IS NULL THEN 1
        WHEN t.source_file IS NULL THEN 2
        WHEN t.mart_rows != p.mart_rows
          OR t.bidder_count != p.bidder_count
          OR t.awarded_bidder IS DISTINCT FROM p.awarded_bidder
          OR t.unmapped_items != p.unmapped_items THEN 3
        ELSE 4
      END,
      source_file
"""))