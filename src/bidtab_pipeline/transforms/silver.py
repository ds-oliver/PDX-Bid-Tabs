"""silver_bid_items build: port of reference notebook 02.

Loads the Silver config through config_loader, registers the temp views and
the normalize_description UDF, writes ref_awarded_bids, and builds
silver_bid_items with 02's SQL. The SQL text is extracted unchanged from the
reference; only the table names come from Settings (checked by
tests/unit/test_verbatim_ports.py). Printed output and the check queries match
the reference exactly.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StringType

from bidtab_pipeline.config_loader.silver_config import (
    AWARDED_BIDS_FILE,
    CONCAT_FIXES_FILE,
    CONTRACTOR_MAPPING_FILE,
    TEXT_NORMALIZATION_FILE,
    UNIT_MAPPING_FILE,
    load_awarded_bids,
    load_concat_fixes,
    load_contractor_aliases,
    load_text_normalizations,
    load_unit_mapping,
    make_normalize_description,
)
from bidtab_pipeline.settings import Settings

BRONZE_TABLE_NAME = "bronze_raw_rows"
SILVER_TABLE_NAME = "silver_bid_items"
AWARDED_TABLE_NAME = "ref_awarded_bids"

# Unchanged from 02. Placeholders: {BRONZE_TABLE}, {SILVER_TABLE}.
SILVER_SQL_TEMPLATE = """
CREATE OR REPLACE TABLE {SILVER_TABLE} AS
WITH bronze_clean AS (
  SELECT
    *,
    CASE
      WHEN airport_name = 'HILLSBOROAIRPORT' THEN 'HILLSBORO AIRPORT'
      WHEN airport_name RLIKE '[A-Z]AIRPORT$'
        THEN REGEXP_REPLACE(airport_name, '([A-Z])AIRPORT$', '$1 AIRPORT')
      ELSE airport_name
    END AS airport_name_clean
  FROM {BRONZE_TABLE}
)
SELECT
  -- Source lineage
  b.source_file,
  b.source_sheet,
  b.bid_type,
  CASE WHEN b.bid_type LIKE '%Alternate%' THEN 'ALT' ELSE 'BASE' END AS tab_type,

  -- Project attributes
  b.ean,
  b.project_name,
  b.airport_name_clean AS airport_name,
  CONCAT(b.airport_name_clean, ' ', b.project_name) AS project_name_full,

  -- Solicitation
  b.solicitation_no AS solicitation_no_raw,
  TRIM(REGEXP_REPLACE(b.solicitation_no, '\\\\|.*$', '')) AS solicitation_no,

  -- Dates
  b.bid_date,
  YEAR(b.bid_date) AS bid_year,

  -- Pay item
  b.item_no,
  TRY_CAST(b.item_no AS DOUBLE) AS item_no_sort,
  b.item_description_raw,
  UPPER(TRIM(b.item_description_raw)) AS item_description_clean,
  normalize_description(UPPER(TRIM(b.item_description_raw))) AS item_description_normalized,
  b.estimated_quantity,

  -- Unit: keep raw passthrough and add standardized version
  b.unit AS unit,
  CASE
    WHEN UPPER(TRIM(b.unit)) IN ('LS','L.S.','LUMP SUM')                           THEN 'LS'
    WHEN UPPER(TRIM(b.unit)) IN ('EA','EACH','EACHS')                              THEN 'EA'
    WHEN UPPER(TRIM(b.unit)) IN ('LF','L.F.','LIN FT','LINEAR FT','LINEAR FEET')   THEN 'LF'
    WHEN UPPER(TRIM(b.unit)) IN ('CY','C.Y.','CU YD','CUBIC YARD','CUBIC YARDS')   THEN 'CY'
    WHEN UPPER(TRIM(b.unit)) IN ('SY','S.Y.','SQ YD','SQUARE YARD','SQUARE YARDS') THEN 'SY'
    WHEN UPPER(TRIM(b.unit)) IN ('SF','S.F.','SQ FT','SQUARE FOOT','SQUARE FEET')  THEN 'SF'
    WHEN UPPER(TRIM(b.unit)) IN ('TON','TONS','T')                                 THEN 'TON'
    WHEN UPPER(TRIM(b.unit)) IN ('GAL','GALLON','GALLONS')                         THEN 'GAL'
    WHEN UPPER(TRIM(b.unit)) IN ('LB','LBS','POUND','POUNDS')                      THEN 'LB'
    WHEN UPPER(TRIM(b.unit)) IN ('ACRE','ACRES','AC')                              THEN 'ACRE'
    ELSE UPPER(TRIM(b.unit))
  END AS unit_clean,

  -- Contractor
  UPPER(TRIM(b.contractor_name)) AS contractor_name_clean,
  COALESCE(a.contractor_name_canonical, UPPER(TRIM(b.contractor_name))) AS awarded_bidder_canonical,
  b.contractor_position,
  b.is_engineers_estimate,
  CASE WHEN aw.award_amount IS NOT NULL THEN TRUE ELSE FALSE END AS is_awarded_bid,

  -- Pricing
  b.unit_price,
  b.total_price,

  -- QA flags
  (b.unit_price IS NULL) AS unit_price_null_flag,
  (b.total_price = 0 OR b.total_price IS NULL) AS total_price_zero_flag,
  (b.total_price = 0 AND b.estimated_quantity > 0) AS price_suspicious_flag,

  -- Timestamps (Bronze→Silver lineage)
  b.bronze_loaded_at,
  current_timestamp() AS silver_loaded_at

FROM bronze_clean b
LEFT JOIN contractor_alias_mapping a
  ON UPPER(TRIM(b.contractor_name)) = a.contractor_name_clean
LEFT JOIN awarded_bids aw
  ON TRIM(REGEXP_REPLACE(b.solicitation_no, '\\\\|.*$', '')) = aw.invitation_no
 AND COALESCE(a.contractor_name_canonical, UPPER(TRIM(b.contractor_name))) = aw.awarded_bidder_canonical
 AND aw.award_amount IS NOT NULL
WHERE b.is_section_header = FALSE
  AND b.item_no IS NOT NULL
  AND b.item_description_raw != '#REF!'
  AND TRIM(b.item_description_raw) != '0'
"""


def build_silver(spark: SparkSession, settings: Settings) -> None:
    """Load Silver config, write ref_awarded_bids, and rebuild silver_bid_items."""
    CONTRACTOR_MAPPING_PATH = settings.config_file(CONTRACTOR_MAPPING_FILE)
    AWARDED_BIDS_PATH = settings.config_file(AWARDED_BIDS_FILE)
    CONCAT_FIXES_PATH = settings.config_file(CONCAT_FIXES_FILE)
    TEXT_NORMALIZATION_PATH = settings.config_file(TEXT_NORMALIZATION_FILE)
    UNIT_MAPPING_PATH = settings.config_file(UNIT_MAPPING_FILE)
    AWARDED_TABLE = settings.table(AWARDED_TABLE_NAME)

    # Load contractor alias mapping into temp view
    _contractor_df = spark.createDataFrame(load_contractor_aliases(CONTRACTOR_MAPPING_PATH))
    _contractor_df.createOrReplaceTempView("contractor_alias_mapping")
    print(f"Loaded {_contractor_df.count()} contractor alias mappings.")

    # Load unit mapping into temp view (not read by any query; docs/backlog.md B-05)
    _unit_df = spark.createDataFrame(load_unit_mapping(UNIT_MAPPING_PATH))
    _unit_df.createOrReplaceTempView("unit_mapping")
    print(f"Loaded {_unit_df.count()} unit mappings from {UNIT_MAPPING_PATH}")

    # Load awarded bids reference data
    _awarded_df = spark.createDataFrame(load_awarded_bids(AWARDED_BIDS_PATH, CONTRACTOR_MAPPING_PATH))
    _awarded_df.createOrReplaceTempView("awarded_bids")
    print(f"Loaded {_awarded_df.count()} awarded bid records.")

    _awarded_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(AWARDED_TABLE)
    print(f"Persisted awarded_bids as {AWARDED_TABLE}")

    # Concat fixes and text normalization aliases from config CSVs
    CONCAT_FIXES = load_concat_fixes(CONCAT_FIXES_PATH)
    print(f"Loaded {len(CONCAT_FIXES)} concat fix patterns from {CONCAT_FIXES_PATH}")
    TEXT_NORMALIZATIONS = load_text_normalizations(TEXT_NORMALIZATION_PATH)
    print(f"Loaded {len(TEXT_NORMALIZATIONS)} text normalization aliases from {TEXT_NORMALIZATION_PATH}")

    normalize_description = make_normalize_description(CONCAT_FIXES, TEXT_NORMALIZATIONS)
    spark.udf.register("normalize_description", normalize_description, StringType())

    spark.sql(
        SILVER_SQL_TEMPLATE.format(
            BRONZE_TABLE=settings.table(BRONZE_TABLE_NAME),
            SILVER_TABLE=settings.table(SILVER_TABLE_NAME),
        )
    )


# Unchanged from 02, in display order. Placeholder: {SILVER_TABLE}.
SILVER_CHECKS = [
    """SELECT COUNT(*) AS total_rows FROM {SILVER_TABLE}""",
    """
        SELECT
          ean,
          bid_type,
          tab_type,
          bid_year,
          COUNT(*) AS row_count,
          COUNT(DISTINCT contractor_name_clean) AS bidder_count,
          COUNT(DISTINCT item_no) AS item_count,
          SUM(CASE WHEN price_suspicious_flag THEN 1 ELSE 0 END) AS suspicious_price_rows
        FROM {SILVER_TABLE}
        GROUP BY ean, bid_type, tab_type, bid_year
        ORDER BY ean, bid_type
        """,
    """
        SELECT
          ean,
          solicitation_no_raw,
          solicitation_no,
          project_name,
          project_name_full
        FROM {SILVER_TABLE}
        WHERE solicitation_no_raw != solicitation_no
           OR solicitation_no_raw LIKE '%|%'
        GROUP BY ean, solicitation_no_raw, solicitation_no, project_name, project_name_full
        """,
    """
        SELECT
          ean,
          solicitation_no,
          project_name_full,
          awarded_bidder_canonical,
          is_awarded_bid,
          COUNT(*) AS row_count
        FROM {SILVER_TABLE}
        WHERE is_awarded_bid = TRUE
        GROUP BY ean, solicitation_no, project_name_full, awarded_bidder_canonical, is_awarded_bid
        ORDER BY ean
        """,
    """
        SELECT
          COUNT(DISTINCT ean) AS total_projects,
          COUNT(DISTINCT CASE WHEN is_awarded_bid THEN ean END) AS projects_with_awarded_bidder,
          COUNT(*) AS total_rows,
          SUM(CASE WHEN is_awarded_bid THEN 1 ELSE 0 END) AS awarded_bidder_rows,
          ROUND(SUM(CASE WHEN is_awarded_bid THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS awarded_pct
        FROM {SILVER_TABLE}
        """,
    """
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT item_description_clean) AS unique_clean,
          COUNT(DISTINCT item_description_normalized) AS unique_normalized,
          COUNT(DISTINCT item_description_clean) - COUNT(DISTINCT item_description_normalized) AS descriptions_collapsed
        FROM {SILVER_TABLE}
        """,
    """
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN unit_price_null_flag THEN 1 ELSE 0 END) AS unit_price_null_count,
          SUM(CASE WHEN total_price_zero_flag THEN 1 ELSE 0 END) AS total_price_zero_count,
          SUM(CASE WHEN price_suspicious_flag THEN 1 ELSE 0 END) AS price_suspicious_count
        FROM {SILVER_TABLE}
        """,
    """
        SELECT
          unit AS unit_raw,
          unit_clean,
          COUNT(*) AS row_count
        FROM {SILVER_TABLE}
        GROUP BY unit, unit_clean
        ORDER BY row_count DESC
        """,
    """
        SELECT
          awarded_bidder_canonical,
          COUNT(DISTINCT contractor_name_clean) AS variant_count,
          COUNT(DISTINCT ean) AS project_count,
          COUNT(*) AS row_count,
          COLLECT_SET(contractor_name_clean) AS clean_name_variants
        FROM {SILVER_TABLE}
        GROUP BY awarded_bidder_canonical
        ORDER BY project_count DESC, row_count DESC
        """,
    """
        SELECT
          contractor_name_clean,
          awarded_bidder_canonical,
          COUNT(*) AS row_count
        FROM {SILVER_TABLE}
        WHERE contractor_name_clean = awarded_bidder_canonical
        GROUP BY contractor_name_clean, awarded_bidder_canonical
        ORDER BY row_count DESC
        """,
    """
        SELECT
          source_file,
          ean,
          item_no,
          item_description_raw,
          contractor_name_clean,
          estimated_quantity,
          unit_price,
          total_price,
          unit_price_null_flag,
          total_price_zero_flag,
          price_suspicious_flag
        FROM {SILVER_TABLE}
        WHERE price_suspicious_flag = TRUE
        ORDER BY source_file, item_no
        LIMIT 50
        """,
    """SELECT airport_name, COUNT(DISTINCT ean) AS projects, COUNT(*) AS rows
FROM {SILVER_TABLE}
GROUP BY airport_name ORDER BY airport_name""",
    """
        SELECT
          is_engineers_estimate,
          COUNT(*) AS row_count,
          COUNT(DISTINCT ean) AS project_count,
          COUNT(DISTINCT contractor_name_clean) AS distinct_names,
          SUM(CASE WHEN unit_price IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_unit_price
        FROM {SILVER_TABLE}
        GROUP BY is_engineers_estimate
        ORDER BY is_engineers_estimate
        """,
]


def silver_checks(spark: SparkSession, settings: Settings) -> list[DataFrame]:
    """The checks 02 displays after the build, in order."""
    silver_table = settings.table(SILVER_TABLE_NAME)
    return [spark.sql(q.format(SILVER_TABLE=silver_table)) for q in SILVER_CHECKS]
