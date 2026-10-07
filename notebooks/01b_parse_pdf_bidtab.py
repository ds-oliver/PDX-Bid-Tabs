# Databricks notebook source
# MAGIC %md
# MAGIC # 01b Parse compiled bid tab PDFs (PDF Bronze)
# MAGIC
# MAGIC **Purpose:** Read every compiled bid tab PDF in the PDF landing volume and write file, item, and control-total rows.
# MAGIC This is the parallel PDF path (BRD MVP); it never writes to the xlsx-path tables.
# MAGIC
# MAGIC **Inputs:** the PDF landing volume (job parameter `bidtab_pdf_landing_root`), top level only. Separate from
# MAGIC `source_files`.
# MAGIC
# MAGIC **Outputs:** in the isolated PDF target (job parameter `bidtab_pdf_target_prefix`; never `pop-poc.bidtab`):
# MAGIC - `ref_file_manifest`: one row per file, with SHA-256, page count, parse status, and reason.
# MAGIC - `bronze_pdf_bid_items`: one row per item, bidder, and schedule; same columns as `bronze_raw_rows` plus page
# MAGIC   number, spec reference, and schedule.
# MAGIC - `bronze_pdf_control_totals`: summary-page and detail total rows per bidder and schedule.
# MAGIC
# MAGIC **Business logic:**
# MAGIC - Rejects files that are not PDFs or have no text layer. A file with the same content as one already read is
# MAGIC   ingested once.
# MAGIC - Reads the header block, the page 1 summary totals, and the detail tables; joins wrapped descriptions with single
# MAGIC   spaces and keeps the spec reference.
# MAGIC - Keeps Engineer's Estimate rows with `is_engineers_estimate`; keeps total rows only as control totals.
# MAGIC - A file whose layout does not match the known compiled bid tab is flagged with a reason and contributes no rows.
# MAGIC - Prints a reconciliation summary: summary totals vs the sum of item totals, within $1.00.
# MAGIC
# MAGIC Code: `src/bidtab_pipeline/sources/pdf/`.

# COMMAND ----------

# Make the repo's src/ importable when this notebook runs from a Databricks Git folder.
import os
import sys

_src = os.path.abspath(os.path.join(os.getcwd(), "..", "src"))
if os.path.isdir(_src) and _src not in sys.path:
    sys.path.insert(0, _src)

# COMMAND ----------

from bidtab_pipeline.settings import Settings
from bidtab_pipeline.sources.pdf.bronze import build_pdf_bronze

settings = Settings.resolve(dbutils)
result = build_pdf_bronze(spark, settings, dbutils=dbutils)

# COMMAND ----------

# Files that were not parsed, with the reason.
display(
    spark.table(settings.pdf_table("ref_file_manifest")).where("parse_status != 'parsed' OR error_text IS NOT NULL")
)
