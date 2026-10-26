"""Shared Silver, crosswalk, and mart on PDF Bronze (Phase 4b; BRD E4, E5).

The xlsx-path transforms run unchanged: build_silver, build_int_crosswalk,
build_mart, and build_unmapped_view are called with a Settings whose table
prefix is the isolated PDF target, so every table they read and write lives
there (NFR-05). Config files are read from the same config volume as the xlsx
path (FR-30).

The one adapter: bronze_raw_rows in the PDF target is bronze_pdf_bid_items
projected onto the xlsx Bronze contract (DR-02 is a superset of it). PDF
lineage columns (page_no, spec_ref_raw, schedule_label, file_sha256) stay in
bronze_pdf_bid_items.
"""

from __future__ import annotations

import dataclasses

from pyspark.sql import SparkSession

from bidtab_pipeline.contracts import BRONZE_RAW_ROWS
from bidtab_pipeline.settings import Settings
from bidtab_pipeline.sources.pdf.bronze import ITEMS_TABLE
from bidtab_pipeline.transforms.crosswalk import build_int_crosswalk
from bidtab_pipeline.transforms.mart import build_mart, build_unmapped_view
from bidtab_pipeline.transforms.silver import build_silver

BRONZE_TABLE_NAME = "bronze_raw_rows"


def pdf_path_settings(settings: Settings) -> Settings:
    """The same settings with tables in the isolated PDF target. Raises unless that target is set and not production."""
    settings.pdf_table(BRONZE_TABLE_NAME)  # SettingMissing / ProductionWriteRefused
    return dataclasses.replace(settings, table_prefix=settings.pdf_target_prefix, allow_production_write=False)


def build_pdf_shared(spark: SparkSession, settings: Settings, INCLUDE_ENG_EST: bool = False) -> Settings:  # noqa: N803
    """Project PDF Bronze onto bronze_raw_rows, then run 02, 03, and 04's mart and unmapped view in the PDF target."""
    pdf = pdf_path_settings(settings)
    columns = [name for name, _ in BRONZE_RAW_ROWS]
    (
        spark.table(settings.pdf_table(ITEMS_TABLE))
        .select(*columns)
        .write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(pdf.table(BRONZE_TABLE_NAME))
    )
    build_silver(spark, pdf)
    build_int_crosswalk(spark, pdf)
    build_mart(spark, pdf, INCLUDE_ENG_EST)
    build_unmapped_view(spark, pdf)
    return pdf
