# Databricks notebook source
# MAGIC %md
# MAGIC # 05 Export CSV snapshots
# MAGIC
# MAGIC **Purpose:** Save a CSV copy of each pipeline table for review outside Databricks.
# MAGIC
# MAGIC **Inputs:** `bronze_raw_rows`, `silver_bid_items`, `mart_bid_analysis`, `ref_awarded_bids`, `int_crosswalk`,
# MAGIC `crosswalk_unmapped_items` in `pop-poc.bidtab`.
# MAGIC
# MAGIC **Outputs:** `/Volumes/pop-poc/bidtab/exports/<table>.csv`, overwritten each run.
# MAGIC
# MAGIC **Business logic:** None; each table is written as is.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/io/exports.py`.

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

from bidtab_pipeline.io.exports import export_csvs
from bidtab_pipeline.settings import Settings

export_csvs(spark, Settings.from_environment(), dbutils=dbutils)
