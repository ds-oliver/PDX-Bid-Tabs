# Databricks notebook source
# MAGIC %md
# MAGIC # 03 Load the pay item crosswalk
# MAGIC
# MAGIC **Purpose:** Load the catalog crosswalk that maps each raw pay item description to a catalog item.
# MAGIC
# MAGIC **Inputs:** `/Volumes/pop-poc/bidtab/config/Final_Recommended_Line_Item_List.csv`; `pop-poc.bidtab.silver_bid_items` (checks only).
# MAGIC
# MAGIC **Outputs:** `pop-poc.bidtab.int_crosswalk` (full overwrite). Cost code QA report and coverage checks below.
# MAGIC
# MAGIC **Business logic:**
# MAGIC - Stops the job if a required column is missing, `item_description_raw` or `item_description_normalized` is blank,
# MAGIC   two rows share the same description (ignoring case and outer spaces), or `spec_type` is not FAA, PORT, or UNK.
# MAGIC - Uppercases `spec_type`. Fills a blank `catalog_division` with `99 Uncategorized / Not Listed`.
# MAGIC - Repairs cost codes: restores leading zeros on Port section codes, trims spaces, uppercases FAA codes.
# MAGIC - Splits `catalog_cost_code` into `faa_item_code` and `port_section_code`.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/config_loader/crosswalk.py`, `src/bidtab_pipeline/transforms/crosswalk.py`.

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

from bidtab_pipeline.settings import Settings
from bidtab_pipeline.transforms.crosswalk import build_int_crosswalk, cost_code_qa, crosswalk_checks

settings = Settings.resolve(dbutils)
crosswalk_df = build_int_crosswalk(spark, settings)

# COMMAND ----------

# Cost code QA report: auto-repairs and remaining anomalies. Fix ANOMALY rows in the source CSV and rerun.
qa = cost_code_qa(spark, crosswalk_df)
if qa is not None:
    display(qa)

# COMMAND ----------

# Row count, spec_type breakdown, Silver coverage, unmatched descriptions, table schema, sample join.
for check in crosswalk_checks(spark, settings):
    display(check)
