# Databricks notebook source
# MAGIC %md
# MAGIC # 01 Parse bid tab workbooks (Bronze)
# MAGIC
# MAGIC **Purpose:** Read every bid tab workbook in the source volume and write one row per pay item and bidder.
# MAGIC
# MAGIC **Inputs:** `/Volumes/pop-poc/bidtab/source_files/*.xlsx` (top level only; subfolders and `~$` lock files are ignored).
# MAGIC
# MAGIC **Outputs:** `pop-poc.bidtab.bronze_raw_rows` (full overwrite). Job log: one line per workbook, then a summary.
# MAGIC
# MAGIC **Business logic:**
# MAGIC - Parses the sheets named `Base Bid Tab` and `Alternate Bid Tab`, `Alternate Bid Tab 1` to `4` (case-insensitive).
# MAGIC - Finds the table header row (`Item No.`, `Item Description`, `Estimated Quantity`, `Units`, and a `Unit Price` / `Total Price` pair per bidder).
# MAGIC - Reads project name, airport, EAN, solicitation number, and bid date from the rows above the table.
# MAGIC - Keeps Engineer's Estimate columns and flags them `is_engineers_estimate`; notebook 04 decides whether they reach the mart.
# MAGIC - Skips `PDX_2017D013.xlsx`.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/sources/xlsx/`.

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

from bidtab_pipeline.settings import Settings
from bidtab_pipeline.sources.xlsx.bronze import build_bronze

build_bronze(spark, Settings.from_environment(), dbutils=dbutils)
