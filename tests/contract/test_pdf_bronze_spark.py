"""The PDF Bronze writer lands DR-01 to DR-03 in the isolated target with the contract schemas."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from bidtab_pipeline.contracts import PDF_PATH_TABLES
from bidtab_pipeline.settings import ProductionWriteRefused, SettingMissing, Settings
from bidtab_pipeline.sources.pdf.bronze import build_pdf_bronze

pytestmark = pytest.mark.spark
PDF_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "pdf"


@pytest.fixture(scope="module")
def landing(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("pdf_landing_spark")
    for name in ("2024-10564 Bid Tab.pdf", "2024-10691 Bid Tab.pdf"):
        shutil.copy2(PDF_DIR / name, root / name)
    (root / "notes.txt").write_text("not a pdf\n")
    return root


def test_writes_contract_schemas_to_isolated_target(spark, landing):
    spark.sql("DROP DATABASE IF EXISTS rf_pdf CASCADE")
    spark.sql("CREATE DATABASE rf_pdf")
    settings = Settings(table_prefix="`rf_xlsx`", pdf_target_prefix="`rf_pdf`", pdf_landing_root=str(landing))
    build_pdf_bronze(spark, settings)
    for table, columns in PDF_PATH_TABLES.items():
        df = spark.table(f"`rf_pdf`.`{table}`")
        assert tuple((f.name, f.dataType.simpleString()) for f in df.schema.fields) == columns
    assert spark.table("`rf_pdf`.`ref_file_manifest`").count() == 3
    assert spark.table("`rf_pdf`.`bronze_pdf_bid_items`").count() == 14 + 65

    # A re-run keeps first_seen_at (FR-02).
    before = {r.file_name: r.first_seen_at for r in spark.table("`rf_pdf`.`ref_file_manifest`").collect()}
    build_pdf_bronze(spark, settings)
    after = {r.file_name: r.first_seen_at for r in spark.table("`rf_pdf`.`ref_file_manifest`").collect()}
    assert after == before


def test_refuses_without_isolated_target(spark, landing):
    with pytest.raises(SettingMissing):
        build_pdf_bronze(spark, Settings(pdf_landing_root=str(landing)))
    with pytest.raises(ProductionWriteRefused):
        build_pdf_bronze(
            spark,
            Settings(
                pdf_target_prefix="`pop-poc`.`bidtab`", allow_production_write=True, pdf_landing_root=str(landing)
            ),
        )
