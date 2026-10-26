"""Post-run Delta report: port of reference notebook 04's last cell.

Compares this run's files to the previous run's in pipeline_file_log: new,
removed, and changed files. Query unchanged from 04; table names come from Settings.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession

from bidtab_pipeline.settings import Settings


def delta_report(spark: SparkSession, settings: Settings) -> DataFrame:
    FILE_LOG_TABLE = settings.table("pipeline_file_log")

    # === POST-RUN DELTA REPORT ===
    # Compares this run's files to the previous run's files.
    # Surfaces: new files ingested, files removed, and any meaningful changes (rows, bidders, awarded contractor, unmapped counts).
    # This is the first thing to read after a pipeline run to confirm any intended changes landed
    # and that nothing else changed unexpectedly.

    return spark.sql(f"""
        WITH this_run AS (
          SELECT * FROM {FILE_LOG_TABLE}
          WHERE run_id = (
            SELECT run_id FROM {FILE_LOG_TABLE}
            ORDER BY run_timestamp DESC LIMIT 1
          )
        ),
        prev_run AS (
          SELECT * FROM {FILE_LOG_TABLE}
          WHERE run_id = (
            SELECT run_id FROM {FILE_LOG_TABLE}
            WHERE run_timestamp < (SELECT MAX(run_timestamp) FROM {FILE_LOG_TABLE})
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
    """)
