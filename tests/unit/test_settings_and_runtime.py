"""Settings resolution, the production write guard, and runtime fallbacks."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from bidtab_pipeline import runtime
from bidtab_pipeline.io.volumes import list_entry_names, make_dirs
from bidtab_pipeline.settings import (
    PROD_TABLE_PREFIX,
    ProductionWriteRefused,
    SettingMissing,
    Settings,
)

SRC = Path(__file__).resolve().parents[2] / "src" / "bidtab_pipeline"
ENV = [
    "BIDTAB_TABLE_PREFIX",
    "BIDTAB_VOLUME_ROOT",
    "BIDTAB_EXPORTS_ROOT",
    "BIDTAB_ALLOW_PRODUCTION_WRITE",
    "BIDTAB_PDF_TARGET_PREFIX",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


class FakeWidgets:
    def __init__(self, values):
        self.values = values

    def get(self, name):
        if name not in self.values:
            raise RuntimeError(f"InputWidgetNotDefined: {name}")  # what Databricks does
        return self.values[name]


class FakeDbutils:
    def __init__(self, widgets):
        self.widgets = FakeWidgets(widgets)


# --- resolution ------------------------------------------------------------------


def test_defaults_are_production_and_refuse_writes():
    s = Settings.resolve()
    assert s.table("mart_bid_analysis") == "`pop-poc`.`bidtab`.`mart_bid_analysis`"
    assert s.volume("source_files") == "/Volumes/pop-poc/bidtab/source_files"
    assert s.exports_dir == "/Volumes/pop-poc/bidtab/exports"
    assert s.allow_production_write is False
    assert s.pdf_target_prefix is None


def test_widgets_override_environment(monkeypatch):
    monkeypatch.setenv("BIDTAB_TABLE_PREFIX", "`from_env`")
    dbutils = FakeDbutils({"bidtab_table_prefix": "`pop-poc`.`bidtab_test`", "bidtab_allow_production_write": "false"})
    assert Settings.resolve(dbutils).table_prefix == "`pop-poc`.`bidtab_test`"


def test_environment_used_when_widget_missing_or_blank(monkeypatch):
    monkeypatch.setenv("BIDTAB_TABLE_PREFIX", "`local_db`")
    monkeypatch.setenv("BIDTAB_VOLUME_ROOT", "/tmp/volumes/")
    s = Settings.resolve(FakeDbutils({"bidtab_table_prefix": ""}))
    assert s.table_prefix == "`local_db`"
    assert s.volume_root == "/tmp/volumes"


def test_dbutils_without_widgets_falls_back_to_environment(monkeypatch):
    """The harness's dbutils shim has fs only."""
    monkeypatch.setenv("BIDTAB_TABLE_PREFIX", "`local_db`")
    assert Settings.resolve(object()).table_prefix == "`local_db`"


def test_bad_boolean_is_an_error():
    with pytest.raises(ValueError):
        Settings.resolve(FakeDbutils({"bidtab_allow_production_write": "maybe"}))


# --- write guard -----------------------------------------------------------------


@pytest.mark.parametrize("prefix", [PROD_TABLE_PREFIX, "pop-poc.bidtab", "`POP-POC`.`BIDTAB`"])
def test_production_table_write_refused_without_flag(prefix):
    with pytest.raises(ProductionWriteRefused):
        Settings(table_prefix=prefix).require_table_write()


def test_production_write_allowed_with_flag():
    Settings(allow_production_write=True).require_table_write()
    Settings(allow_production_write=True).require_export_write()


def test_isolated_tables_but_production_exports_still_refused():
    s = Settings(table_prefix="`pop-poc`.`bidtab_gate2c`")
    s.require_table_write()
    with pytest.raises(ProductionWriteRefused):
        s.require_export_write()


def test_fully_isolated_run_is_allowed():
    s = Settings(table_prefix="`pop-poc`.`bidtab_gate2c`", exports_root="/Volumes/pop-poc/bidtab_gate2c/exports")
    s.require_table_write()
    s.require_export_write()


def test_pdf_target_has_no_default_and_is_never_production():
    with pytest.raises(SettingMissing):
        Settings().pdf_table("bronze_pdf_bid_items")
    with pytest.raises(ProductionWriteRefused):
        Settings(pdf_target_prefix=PROD_TABLE_PREFIX, allow_production_write=True).pdf_table("x")
    assert Settings(pdf_target_prefix="`pop-poc`.`bidtab_pdf`").pdf_table("x") == "`pop-poc`.`bidtab_pdf`.`x`"


class ExplodingSpark:
    """Any Spark call fails the test: the guard must refuse before touching Spark."""

    def __getattr__(self, name):
        raise AssertionError(f"spark.{name} called before the write guard")


def _writers():
    from bidtab_pipeline.io.exports import export_csvs
    from bidtab_pipeline.quality.audit_log import log_run
    from bidtab_pipeline.sources.xlsx.bronze import build_bronze
    from bidtab_pipeline.transforms.crosswalk import build_int_crosswalk
    from bidtab_pipeline.transforms.mart import build_mart, build_unmapped_view
    from bidtab_pipeline.transforms.silver import build_silver

    return {
        "build_bronze": lambda sp, st: build_bronze(sp, st),
        "build_silver": lambda sp, st: build_silver(sp, st),
        "build_int_crosswalk": lambda sp, st: build_int_crosswalk(sp, st),
        "build_mart": lambda sp, st: build_mart(sp, st, False),
        "build_unmapped_view": lambda sp, st: build_unmapped_view(sp, st),
        "log_run": lambda sp, st: log_run(sp, st, False),
        "export_csvs": lambda sp, st: export_csvs(sp, st),
    }


@pytest.mark.parametrize("writer", sorted(_writers()))
def test_every_writer_refuses_production_by_default(writer):
    with pytest.raises(ProductionWriteRefused):
        _writers()[writer](ExplodingSpark(), Settings())


# --- runtime and package boundaries ------------------------------------------------


def test_no_src_module_imports_tests_or_harness():
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                assert root not in {"tests", "harness", "scenarios", "snapshot", "conftest"}, f"{path}: {name}"


def test_local_spark_is_only_imported_lazily():
    """io.local_spark needs delta-spark (local extra); nothing may import it at module level."""
    for path in SRC.rglob("*.py"):
        if path.name == "local_spark.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:  # module level only
            if isinstance(node, ast.ImportFrom) and node.module and "local_spark" in node.module:
                raise AssertionError(f"{path} imports local_spark at module level")


def test_get_dbutils_is_none_off_databricks():
    assert runtime.get_dbutils(None) is None


def test_display_falls_back_to_print(capsys):
    runtime.get_display()("hello")
    assert capsys.readouterr().out == "hello\n"


def test_volume_helpers_fall_back_to_local_filesystem(tmp_path):
    make_dirs(str(tmp_path / "a" / "b"))
    (tmp_path / "f.xlsx").write_text("x")
    assert list_entry_names(str(tmp_path)) == ["a/", "f.xlsx"]
