# Databricks notebook source
# Silver layer build for bidtab pipeline.
# Transforms bronze_raw_rows → silver_bid_items.
# Full refresh (CREATE OR REPLACE TABLE). Safe to re-run.

# COMMAND ----------

BRONZE_TABLE = "`pop-poc`.`bidtab`.`bronze_raw_rows`"
SILVER_TABLE = "`pop-poc`.`bidtab`.`silver_bid_items`"
CONTRACTOR_MAPPING_PATH = "/Volumes/pop-poc/bidtab/config/contractor_alias_mapping.csv"
AWARDED_BIDS_PATH = "/Volumes/pop-poc/bidtab/config/AwardedBidsSearchList.xlsx"
CONCAT_FIXES_PATH = "/Volumes/pop-poc/bidtab/config/concat_fixes.csv"
TEXT_NORMALIZATION_PATH = "/Volumes/pop-poc/bidtab/config/text_normalization.csv"
UNIT_MAPPING_PATH = "/Volumes/pop-poc/bidtab/config/unit_mapping.csv"

# COMMAND ----------

# Load contractor alias mapping into temp view
import pandas as pd

_contractor_pdf = pd.read_csv(CONTRACTOR_MAPPING_PATH)
_contractor_df = spark.createDataFrame(_contractor_pdf)
_contractor_df.createOrReplaceTempView("contractor_alias_mapping")
print(f"Loaded {_contractor_df.count()} contractor alias mappings.")

# COMMAND ----------

# Load unit mapping into temp view
_unit_pdf = pd.read_csv(UNIT_MAPPING_PATH)
_unit_df = spark.createDataFrame(_unit_pdf)
_unit_df.createOrReplaceTempView("unit_mapping")
print(f"Loaded {_unit_df.count()} unit mappings from {UNIT_MAPPING_PATH}")

# COMMAND ----------

# Load awarded bids reference data
_awarded_pdf = pd.read_excel(AWARDED_BIDS_PATH, header=4)

_awarded_pdf = _awarded_pdf[
    _awarded_pdf["Award Amount"].notna()
    & _awarded_pdf["Invitation #"].notna()
    & _awarded_pdf["Bidder"].notna()
].copy()

_awarded_pdf["invitation_no"] = _awarded_pdf["Invitation #"].astype(str).str.strip()
_awarded_pdf["award_amount"] = _awarded_pdf["Award Amount"]

_awarded_pdf["awarded_bidder_clean"] = (
    _awarded_pdf["Bidder"]
    .astype(str)
    .str.replace('"', "", regex=False)
    .str.upper()
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)

_contractor_alias_pdf = pd.read_csv(CONTRACTOR_MAPPING_PATH)
_alias_dict = dict(
    zip(
        _contractor_alias_pdf["contractor_name_clean"],
        _contractor_alias_pdf["contractor_name_canonical"],
    )
)
_awarded_pdf["awarded_bidder_canonical"] = _awarded_pdf["awarded_bidder_clean"].map(_alias_dict).fillna(
    _awarded_pdf["awarded_bidder_clean"]
)

# Keep award_amount so Silver join can filter on it
_awarded_unique = _awarded_pdf[["invitation_no", "awarded_bidder_canonical", "award_amount"]].drop_duplicates(
    subset=["invitation_no", "awarded_bidder_canonical"]
)

_awarded_df = spark.createDataFrame(_awarded_unique)
_awarded_df.createOrReplaceTempView("awarded_bids")
print(f"Loaded {_awarded_df.count()} awarded bid records.")

_awarded_df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("`pop-poc`.`bidtab`.`ref_awarded_bids`")
print("Persisted awarded_bids as `pop-poc`.`bidtab`.`ref_awarded_bids`")

# COMMAND ----------

import re
import pandas as pd
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

# Load concat fixes from config CSV
_concat_pdf = pd.read_csv(CONCAT_FIXES_PATH)
CONCAT_FIXES = list(zip(_concat_pdf["pattern"], _concat_pdf["replacement"]))
print(f"Loaded {len(CONCAT_FIXES)} concat fix patterns from {CONCAT_FIXES_PATH}")

# Load text normalization aliases from config CSV.
# These are anchored full-string regex aliases (^FROM$ -> TO) that fold known
# cosmetic variants of pay item descriptions to a canonical form. Applied as
# the final step of normalize_description so they operate on already-cleaned,
# uppercased, unit-symbol-standardized strings.
_textnorm_pdf = pd.read_csv(TEXT_NORMALIZATION_PATH, keep_default_na=False)
TEXT_NORMALIZATIONS = list(zip(_textnorm_pdf["pattern"], _textnorm_pdf["replacement"]))
print(f"Loaded {len(TEXT_NORMALIZATIONS)} text normalization aliases from {TEXT_NORMALIZATION_PATH}")


def normalize_description(desc):
    """Apply non-destructive spacing fixes to a pay item description."""
    if desc is None:
        return None
    cleaned = desc.strip()
    for pattern, replacement in CONCAT_FIXES:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'(\d)"', r"\1-INCH", cleaned)
    cleaned = re.sub(r"(\d)'", r"\1-FOOT", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    for pattern, replacement in TEXT_NORMALIZATIONS:
        cleaned = re.sub(pattern, replacement, cleaned)
    return cleaned


normalize_description_udf = udf(normalize_description, StringType())
spark.udf.register("normalize_description", normalize_description, StringType())

# COMMAND ----------

spark.sql("""
CREATE OR REPLACE TABLE `pop-poc`.`bidtab`.`silver_bid_items` AS
WITH bronze_clean AS (
  SELECT
    *,
    CASE
      WHEN airport_name = 'HILLSBOROAIRPORT' THEN 'HILLSBORO AIRPORT'
      WHEN airport_name RLIKE '[A-Z]AIRPORT$'
        THEN REGEXP_REPLACE(airport_name, '([A-Z])AIRPORT$', '$1 AIRPORT')
      ELSE airport_name
    END AS airport_name_clean
  FROM `pop-poc`.`bidtab`.`bronze_raw_rows`
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
""")

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS total_rows FROM {SILVER_TABLE}"))

# COMMAND ----------

display(
    spark.sql(
        f"""
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
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
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
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
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
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          COUNT(DISTINCT ean) AS total_projects,
          COUNT(DISTINCT CASE WHEN is_awarded_bid THEN ean END) AS projects_with_awarded_bidder,
          COUNT(*) AS total_rows,
          SUM(CASE WHEN is_awarded_bid THEN 1 ELSE 0 END) AS awarded_bidder_rows,
          ROUND(SUM(CASE WHEN is_awarded_bid THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS awarded_pct
        FROM {SILVER_TABLE}
        """
    )
)

# COMMAND ----------

# Normalization coverage check
display(
    spark.sql(
        f"""
        SELECT
          COUNT(*) AS total_rows,
          COUNT(DISTINCT item_description_clean) AS unique_clean,
          COUNT(DISTINCT item_description_normalized) AS unique_normalized,
          COUNT(DISTINCT item_description_clean) - COUNT(DISTINCT item_description_normalized) AS descriptions_collapsed
        FROM {SILVER_TABLE}
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN unit_price_null_flag THEN 1 ELSE 0 END) AS unit_price_null_count,
          SUM(CASE WHEN total_price_zero_flag THEN 1 ELSE 0 END) AS total_price_zero_count,
          SUM(CASE WHEN price_suspicious_flag THEN 1 ELSE 0 END) AS price_suspicious_count
        FROM {SILVER_TABLE}
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          unit AS unit_raw,
          unit_clean,
          COUNT(*) AS row_count
        FROM {SILVER_TABLE}
        GROUP BY unit, unit_clean
        ORDER BY row_count DESC
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
        SELECT
          awarded_bidder_canonical,
          COUNT(DISTINCT contractor_name_clean) AS variant_count,
          COUNT(DISTINCT ean) AS project_count,
          COUNT(*) AS row_count,
          COLLECT_SET(contractor_name_clean) AS clean_name_variants
        FROM {SILVER_TABLE}
        GROUP BY awarded_bidder_canonical
        ORDER BY project_count DESC, row_count DESC
        """
    )
)

# COMMAND ----------

# Check for unmapped contractor names (these use fallback = contractor_name_clean)
display(
    spark.sql(
        f"""
        SELECT
          contractor_name_clean,
          awarded_bidder_canonical,
          COUNT(*) AS row_count
        FROM {SILVER_TABLE}
        WHERE contractor_name_clean = awarded_bidder_canonical
        GROUP BY contractor_name_clean, awarded_bidder_canonical
        ORDER BY row_count DESC
        """
    )
)

# COMMAND ----------

display(
    spark.sql(
        f"""
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
        """
    )
)

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT airport_name, COUNT(DISTINCT ean) AS projects, COUNT(*) AS rows
# MAGIC FROM `pop-poc`.`bidtab`.`silver_bid_items`
# MAGIC GROUP BY airport_name ORDER BY airport_name

# COMMAND ----------

# Engineer's Estimate ingestion check
display(
    spark.sql(
        f"""
        SELECT
          is_engineers_estimate,
          COUNT(*) AS row_count,
          COUNT(DISTINCT ean) AS project_count,
          COUNT(DISTINCT contractor_name_clean) AS distinct_names,
          SUM(CASE WHEN unit_price IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_unit_price
        FROM {SILVER_TABLE}
        GROUP BY is_engineers_estimate
        ORDER BY is_engineers_estimate
        """
    )
)