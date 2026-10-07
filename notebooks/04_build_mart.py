# Databricks notebook source
# MAGIC %md
# MAGIC # 04 Build the mart
# MAGIC
# MAGIC **Purpose:** Build `mart_bid_analysis`, the single table Power BI reads, and check the run.
# MAGIC
# MAGIC **Inputs:** `pop-poc.bidtab.silver_bid_items`, `pop-poc.bidtab.int_crosswalk`.
# MAGIC
# MAGIC **Outputs:**
# MAGIC - `pop-poc.bidtab.mart_bid_analysis` (full overwrite).
# MAGIC - `pop-poc.bidtab.crosswalk_unmapped_items` view: raw descriptions with no crosswalk row.
# MAGIC - `pop-poc.bidtab.pipeline_run_log` and `pipeline_file_log`: one row per run and per file, appended.
# MAGIC - Run Health Summary and post-run Delta report (last two outputs below). Read these after every run.
# MAGIC
# MAGIC **Business logic:**
# MAGIC - Joins Silver to the crosswalk on the raw description, ignoring case and outer spaces.
# MAGIC   Unmapped rows get `100 - Unmapped` / `UNMAPPED` labels and appear in `crosswalk_unmapped_items`.
# MAGIC - `bid_item_sk` is a SHA-256 of bid type, EAN, item number, and canonical contractor.
# MAGIC - `effective_unit_price` is total price divided by quantity, rounded to cents.
# MAGIC - Engineer's Estimate rows are left out unless `INCLUDE_ENG_EST` below is `True`.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/transforms/mart.py`, `src/bidtab_pipeline/quality/`.

# COMMAND ----------

# Toggle: include Engineer's Estimate rows in the mart.
# Default is False so the mart contains only true contractor bids — matches the
# expectation of existing Power BI measures and avoids skewing contractor averages.
# Flip to True when an analyst wants EE data available for variance/baseline analysis.
# Bronze and Silver always retain EE rows; this only controls what reaches the mart.
INCLUDE_ENG_EST = False

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

from bidtab_pipeline.quality.audit_log import log_run
from bidtab_pipeline.quality.delta_report import delta_report
from bidtab_pipeline.quality.run_health import run_health
from bidtab_pipeline.settings import Settings
from bidtab_pipeline.transforms.mart import build_mart, build_unmapped_view, ee_toggle_check, mart_checks

settings = Settings.resolve(dbutils)
build_mart(spark, settings, INCLUDE_ENG_EST)
display(ee_toggle_check(spark, settings, INCLUDE_ENG_EST))

# COMMAND ----------

build_unmapped_view(spark, settings)

# COMMAND ----------

# Unmapped items; mart vs Silver; catalog coverage; projects; top catalog items; mobilization trend;
# price quality; awarded sample; unmapped detail; spec_type; airports; item number audits; unit price backfill.
for check in mart_checks(spark, settings):
    display(check)

# COMMAND ----------

# === RUN HEALTH SUMMARY ===
# Read this after every pipeline run: layer row counts, Silver-to-mart check, catalog coverage,
# unmapped descriptions, and projects.
display(run_health(spark, settings, INCLUDE_ENG_EST))

# COMMAND ----------

# === RUN-OVER-RUN AUDIT LOG ===
# Appends this run to pipeline_run_log and pipeline_file_log, then shows the last 10 runs.
display(log_run(spark, settings, INCLUDE_ENG_EST))

# COMMAND ----------

# === POST-RUN DELTA REPORT ===
# New, removed, and changed files compared with the previous run. Read this first after a run.
display(delta_report(spark, settings))
