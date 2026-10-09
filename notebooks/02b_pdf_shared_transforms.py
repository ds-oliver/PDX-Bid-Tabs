# Databricks notebook source
# MAGIC %md
# MAGIC # 02b Shared Silver, crosswalk, and mart on PDF Bronze
# MAGIC
# MAGIC **Purpose:** Run the xlsx path's Silver, crosswalk, and mart logic, unchanged, on the PDF Bronze rows, so the PDF
# MAGIC path produces a `mart_bid_analysis` with the same contract for comparison (BRD FR-20 to FR-22, FR-30, FR-31, FR-40).
# MAGIC
# MAGIC **Inputs:** `bronze_pdf_bid_items` in the isolated PDF target (from `01b`); the config files in the config volume
# MAGIC (the same files the xlsx path reads).
# MAGIC
# MAGIC **Outputs:** in the isolated PDF target only (job parameter `bidtab_pdf_target_prefix`; never `pop-poc.bidtab`):
# MAGIC `bronze_raw_rows` (PDF Bronze projected onto the xlsx Bronze columns), `silver_bid_items`, `ref_awarded_bids`,
# MAGIC `int_crosswalk`, `mart_bid_analysis`, and the `crosswalk_unmapped_items` view.
# MAGIC
# MAGIC **Business logic:** identical to notebooks `02`, `03`, and `04` (mart and unmapped view). The mart excludes
# MAGIC Engineer's Estimate rows while `INCLUDE_ENG_EST = False`, as in `04`.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/sources/pdf/shared.py`.

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

INCLUDE_ENG_EST = False

# COMMAND ----------

from bidtab_pipeline.settings import Settings
from bidtab_pipeline.sources.pdf.shared import build_pdf_shared

settings = Settings.resolve(dbutils)
pdf = build_pdf_shared(spark, settings, INCLUDE_ENG_EST)

# COMMAND ----------

# Unmapped descriptions per file (FR-31).
display(
    spark.sql(
        "SELECT source_file, COUNT(*) AS mart_rows, "
        "SUM(CASE WHEN NOT is_catalog_mapped THEN 1 ELSE 0 END) AS unmapped_rows, "
        "COUNT(DISTINCT CASE WHEN NOT is_catalog_mapped THEN item_description_raw END) AS unmapped_descriptions "
        f"FROM {pdf.table('mart_bid_analysis')} GROUP BY source_file ORDER BY source_file"
    )
)
