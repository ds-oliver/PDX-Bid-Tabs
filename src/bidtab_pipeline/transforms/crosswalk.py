"""int_crosswalk build: port of reference notebook 03's write, QA report, and checks.

Printed output, QA report, and check queries match the reference exactly.
"""

from __future__ import annotations

import pandas as pd
from pyspark.sql import DataFrame, SparkSession

from bidtab_pipeline.config_loader.crosswalk import CROSSWALK_FILE, load_crosswalk
from bidtab_pipeline.settings import Settings

CROSSWALK_TABLE_NAME = "int_crosswalk"
SILVER_TABLE_NAME = "silver_bid_items"

CROSSWALK_COLUMNS = [
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
]


def build_int_crosswalk(spark: SparkSession, settings: Settings) -> pd.DataFrame:
    """Load the crosswalk config, write int_crosswalk, print the summary.

    Returns the working DataFrame (with QA columns) for cost_code_qa().
    """
    settings.require_table_write()
    CROSSWALK_TABLE = settings.table(CROSSWALK_TABLE_NAME)
    crosswalk_df = load_crosswalk(settings.config_file(CROSSWALK_FILE))

    # === Final column projection (drop QA-only columns from the Delta table) ===
    _crosswalk_out = crosswalk_df[CROSSWALK_COLUMNS]

    # Write to Delta
    _crosswalk_spark = spark.createDataFrame(_crosswalk_out)
    _crosswalk_spark.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        CROSSWALK_TABLE
    )

    # === Summary print ===
    print(f"Crosswalk table {CROSSWALK_TABLE} built with {_crosswalk_spark.count()} rows.\n")

    print("  spec_type breakdown:")
    print("    " + crosswalk_df["spec_type"].value_counts().to_string().replace("\n", "\n    "))

    _repairs = (crosswalk_df["_repair_note"] != "").sum()
    _anomalies = (crosswalk_df["_code_class"] == "ANOMALY").sum()
    print("\n  catalog_cost_code auto-repair results:")
    print(f"    Repaired:  {_repairs} rows (see Cell 2c for details)")
    print(f"    Anomalies: {_anomalies} rows still don't match FAA or Port pattern (see Cell 2c)")
    print(f"\n  Distinct catalog_division:        {crosswalk_df['catalog_division'].nunique()}")
    print(f"  Distinct catalog_cost_code:       {crosswalk_df['catalog_cost_code'].nunique()}")
    print(f"  Distinct catalog_cost_code_desc:  {crosswalk_df['catalog_cost_code_desc'].nunique()}")
    print(f"  FAA codes populated:              {crosswalk_df['faa_item_code'].notna().sum()}")
    print(f"  Port codes populated:             {crosswalk_df['port_section_code'].notna().sum()}")
    return crosswalk_df


def cost_code_qa(spark: SparkSession, crosswalk_df: pd.DataFrame) -> DataFrame | None:
    """Cost code QA report: auto-repairs and remaining anomalies.

    Anything in the ANOMALY rows will NOT classify into faa_item_code or
    port_section_code on the mart, so Power BI filters by those columns miss
    them. Prints the report header; returns the rows to display, or None.
    """
    _qa = crosswalk_df[(crosswalk_df["_repair_note"] != "") | (crosswalk_df["_code_class"] == "ANOMALY")][
        [
            "item_description_raw",
            "catalog_cost_code_original",
            "catalog_cost_code",
            "_code_class",
            "_repair_note",
            "spec_type",
            "catalog_division",
        ]
    ].rename(
        columns={
            "_code_class": "post_repair_classification",
            "_repair_note": "repair_action",
        }
    )

    if len(_qa) == 0:
        print("✅ No cost code repairs or anomalies — all values cleanly match FAA or Port pattern.")
        return None
    print(f"Cost code QA: {len(_qa)} rows with repairs or anomalies.\n")
    print("  repair_action = 'repaired' → auto-fixed (typically zero-padded). Verify result is correct.")
    print("  repair_action = 'trimmed'  → whitespace stripped.")
    print("  post_repair_classification = 'ANOMALY' → still doesn't match either pattern. Fix the source CSV.\n")
    return spark.createDataFrame(_qa)


def crosswalk_checks(spark: SparkSession, settings: Settings) -> list[DataFrame]:
    """The post-load checks 03 displays, in order."""
    CROSSWALK_TABLE = settings.table(CROSSWALK_TABLE_NAME)
    SILVER_TABLE = settings.table(SILVER_TABLE_NAME)
    return [
        spark.sql(f"SELECT COUNT(*) AS total_rows FROM {CROSSWALK_TABLE}"),
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
        ),
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
        ),
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
        ),
        spark.sql(f"DESCRIBE TABLE {CROSSWALK_TABLE}"),
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
        ),
    ]
