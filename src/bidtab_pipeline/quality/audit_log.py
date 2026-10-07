"""Run-over-run audit log: port of reference notebook 04's audit cell.

Creates pipeline_run_log and pipeline_file_log on first use (append-only Delta
tables), appends this run, and returns the last 10 runs for display. They feed
the post-run Delta report. SQL unchanged from 04; table names come from Settings.
"""

from __future__ import annotations

import uuid

from pyspark.sql import DataFrame, SparkSession

from bidtab_pipeline.settings import Settings


def log_run(spark: SparkSession, settings: Settings, INCLUDE_ENG_EST: bool) -> DataFrame:  # noqa: N803
    settings.require_table_write()
    BRONZE_TABLE = settings.table("bronze_raw_rows")
    SILVER_TABLE = settings.table("silver_bid_items")
    CROSSWALK_TABLE = settings.table("int_crosswalk")
    MART_TABLE = settings.table("mart_bid_analysis")
    UNMAPPED_VIEW = settings.table("crosswalk_unmapped_items")
    RUN_LOG_TABLE = settings.table("pipeline_run_log")
    FILE_LOG_TABLE = settings.table("pipeline_file_log")

    # === RUN-OVER-RUN AUDIT LOG ===
    # Append-only history tables. One row per run summarizes pipeline health;
    # one row per (run, file) captures per-source-file detail used by the delta cell below.
    # Both tables are created on first run; appended thereafter.

    # --- Table 1: run-level audit log ---
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {RUN_LOG_TABLE} (
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
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {FILE_LOG_TABLE} (
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
    run_id = str(uuid.uuid4())[:8]

    # --- Insert the run-level summary row ---
    # EE-toggle-aware silver_to_mart_pass: when INCLUDE_ENG_EST=False, the mart should
    # equal Silver's non-EE row count; when True, mart should equal Silver total.
    spark.sql(f"""
        INSERT INTO {RUN_LOG_TABLE}
        SELECT
          '{run_id}' AS run_id,
          current_timestamp() AS run_timestamp,
          (SELECT COUNT(*) FROM {BRONZE_TABLE}),
          (SELECT COUNT(*) FROM {SILVER_TABLE}),
          (SELECT COUNT(*) FROM {CROSSWALK_TABLE}),
          (SELECT COUNT(*) FROM {MART_TABLE}),
          CASE
            WHEN {str(INCLUDE_ENG_EST).lower()}
              THEN (SELECT COUNT(*) FROM {SILVER_TABLE}) =
                   (SELECT COUNT(*) FROM {MART_TABLE})
            ELSE (SELECT COUNT(*) FROM {SILVER_TABLE} WHERE NOT is_engineers_estimate) =
                 (SELECT COUNT(*) FROM {MART_TABLE})
          END AS silver_to_mart_pass,
          (SELECT ROUND(SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1)
           FROM {MART_TABLE}),
          (SELECT COUNT(*) FROM {UNMAPPED_VIEW}),
          (SELECT COUNT(DISTINCT ean) FROM {MART_TABLE}),
          (SELECT COUNT(DISTINCT CASE WHEN is_awarded_bid THEN ean END) FROM {MART_TABLE}),
          NULL  -- notes — manual annotation field for unusual runs
    """)

    # --- Insert the per-file detail rows ---
    # One row per source workbook currently in the mart, with project metadata and quality flags.
    spark.sql(f"""
        INSERT INTO {FILE_LOG_TABLE}
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
    print("  → pipeline_run_log:  1 row (run summary)")
    print("  → pipeline_file_log: N rows (one per source file)")

    # --- Display the last 10 runs ---
    return spark.sql(f"""
        SELECT * FROM {RUN_LOG_TABLE}
        ORDER BY run_timestamp DESC LIMIT 10
    """)
