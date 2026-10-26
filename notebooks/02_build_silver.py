# Databricks notebook source
# MAGIC %md
# MAGIC # 02 Build Silver
# MAGIC
# MAGIC **Purpose:** Clean the Bronze rows into one standardized row per pay item and bidder.
# MAGIC
# MAGIC **Inputs:** `pop-poc.bidtab.bronze_raw_rows`; config files in `/Volumes/pop-poc/bidtab/config/`:
# MAGIC `contractor_alias_mapping.csv`, `AwardedBidsSearchList.xlsx`, `concat_fixes.csv`, `text_normalization.csv`,
# MAGIC `unit_mapping.csv`.
# MAGIC
# MAGIC **Outputs:** `pop-poc.bidtab.silver_bid_items` and `pop-poc.bidtab.ref_awarded_bids` (full overwrite). Checks below.
# MAGIC
# MAGIC **Business logic:**
# MAGIC - Drops rows with no item number, a `#REF!` description, or a description of `0`.
# MAGIC - Maps contractor names to canonical names with `contractor_alias_mapping.csv`.
# MAGIC - Marks the awarded bid where the solicitation number and canonical bidder match `AwardedBidsSearchList.xlsx`.
# MAGIC - Normalizes descriptions: `concat_fixes.csv` patterns, `"` to `-INCH`, `'` to `-FOOT`, spacing,
# MAGIC   then `text_normalization.csv` aliases.
# MAGIC - Standardizes units (LS, EA, LF, CY, SY, SF, TON, GAL, LB, ACRE) and fixes airport name spacing.
# MAGIC - Flags null unit prices, zero or null totals, and zero totals with a positive quantity.
# MAGIC - Keeps Engineer's Estimate rows with `is_engineers_estimate`.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/config_loader/silver_config.py`, `src/bidtab_pipeline/transforms/silver.py`.

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

from bidtab_pipeline.settings import Settings
from bidtab_pipeline.transforms.silver import build_silver, silver_checks

settings = Settings.resolve(dbutils)
build_silver(spark, settings)

# COMMAND ----------

# Row count; by project and tab; solicitation cleanup; awarded bidders; award coverage; description collapse;
# price flags; units; contractor variants; unmapped contractors; suspicious prices; airports; Engineer's Estimate.
for check in silver_checks(spark, settings):
    display(check)
