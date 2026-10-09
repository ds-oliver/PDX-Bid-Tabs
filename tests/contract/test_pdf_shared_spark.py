"""02b: the shared Silver, crosswalk, and mart run on PDF Bronze in the isolated target (Phase 4b).

Uses the synthetic config, so it runs in CI without production inputs. The PDF descriptions are not in the
synthetic crosswalk, so every mart row is unmapped; the test checks wiring and contracts, not coverage.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bidtab_pipeline.contracts import XLSX_PATH_TABLES
from bidtab_pipeline.settings import ProductionWriteRefused, SettingMissing, Settings
from bidtab_pipeline.sources.pdf.bronze import build_pdf_bronze
from bidtab_pipeline.sources.pdf.shared import build_pdf_shared

pytestmark = pytest.mark.spark
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
# What 02b builds (04's audit tables, run health, and delta report are not part of it).
SHARED_TABLES = ("bronze_raw_rows", "silver_bid_items", "ref_awarded_bids", "int_crosswalk", "mart_bid_analysis")


@pytest.fixture(scope="module")
def pdf_run(spark, tmp_path_factory):
    root = tmp_path_factory.mktemp("pdf_shared")
    landing = root / "landing"
    landing.mkdir()
    for name in ("2024-10564 Bid Tab.pdf", "2024-10691 Bid Tab.pdf"):
        shutil.copy2(FIXTURES / "pdf" / name, landing / name)
    config = root / "volumes" / "config"
    shutil.copytree(FIXTURES / "config_synthetic", config, ignore=shutil.ignore_patterns("guardrail*"))
    for db in ("rf_shared_x", "rf_shared_pdf"):
        spark.sql(f"DROP DATABASE IF EXISTS {db} CASCADE")
        spark.sql(f"CREATE DATABASE {db}")
    settings = Settings(
        table_prefix="`rf_shared_x`",
        volume_root=str(root / "volumes"),
        pdf_target_prefix="`rf_shared_pdf`",
        pdf_landing_root=str(landing),
    )
    build_pdf_bronze(spark, settings)
    pdf = build_pdf_shared(spark, settings, INCLUDE_ENG_EST=False)
    return settings, pdf


def test_writes_only_to_the_pdf_target(spark, pdf_run):
    _, pdf = pdf_run
    assert pdf.table_prefix == "`rf_shared_pdf`"
    tables = spark.sql("SHOW TABLES IN rf_shared_x").collect()
    assert [r.tableName for r in tables if r.namespace == "rf_shared_x"] == []  # session temp views list with ""


def test_shared_tables_keep_the_xlsx_contracts(spark, pdf_run):
    for table in SHARED_TABLES:
        columns = XLSX_PATH_TABLES[table]
        df = spark.table(f"`rf_shared_pdf`.`{table}`")
        assert tuple((f.name, f.dataType.simpleString()) for f in df.schema.fields) == columns, table


def test_mart_rows_and_engineers_estimate(spark, pdf_run):
    bronze = spark.table("`rf_shared_pdf`.`bronze_pdf_bid_items`")
    mart = spark.table("`rf_shared_pdf`.`mart_bid_analysis`")
    assert mart.count() == bronze.where("NOT is_engineers_estimate").count()
    assert spark.table("`rf_shared_pdf`.`silver_bid_items`").count() == bronze.count()
    solicitations = {r.solicitation_no for r in mart.select("solicitation_no").distinct().collect()}
    assert solicitations == {"2024-10564", "2024-10691"}


def test_refuses_without_isolated_target(spark):
    with pytest.raises(SettingMissing):
        build_pdf_shared(spark, Settings())
    with pytest.raises(ProductionWriteRefused):
        build_pdf_shared(spark, Settings(pdf_target_prefix="`pop-poc`.`bidtab`", allow_production_write=True))
