"""Run Health Summary: port of reference notebook 04's single-pane post-run check.

Query unchanged from 04; table names come from Settings.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession

from bidtab_pipeline.settings import Settings


def run_health(spark: SparkSession, settings: Settings, INCLUDE_ENG_EST: bool) -> DataFrame:  # noqa: N803
    BRONZE_TABLE = settings.table("bronze_raw_rows")
    SILVER_TABLE = settings.table("silver_bid_items")
    CROSSWALK_TABLE = settings.table("int_crosswalk")
    MART_TABLE = settings.table("mart_bid_analysis")
    UNMAPPED_VIEW = settings.table("crosswalk_unmapped_items")

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

    return spark.sql(f"""
        WITH layer_counts AS (
          SELECT
            (SELECT COUNT(*) FROM {BRONZE_TABLE})            AS bronze_rows,
            (SELECT COUNT(*) FROM {SILVER_TABLE})           AS silver_rows,
            (SELECT COUNT(*) FROM {SILVER_TABLE}
             WHERE NOT is_engineers_estimate)                                     AS silver_contractor_rows,
            (SELECT COUNT(*) FROM {CROSSWALK_TABLE})              AS crosswalk_rows,
            (SELECT COUNT(*) FROM {MART_TABLE})                                    AS mart_rows,
            (SELECT COUNT(*) FROM {UNMAPPED_VIEW})   AS unmapped_descriptions
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
    """)
