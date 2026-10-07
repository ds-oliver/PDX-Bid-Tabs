"""Synthetic input scenarios for the reference harness.

base_run1     First run on SYN_A and SYN_B, plus files 01 must skip, ignore, or
              report as errors.
base_run2     Second run in the same database: SYN_B removed, SYN_C added,
              SYN_E and SYN_F replaced (rows and bidders change), and the award
              list and crosswalk replaced (SYN_G award and SYN_H unmapped count
              change). 04's Delta report shows every status: NEW, REMOVED,
              CHANGED rows, CHANGED bidders, AWARDED, UNMAPPED, unchanged.
ee_included   base_run1 inputs with 04's INCLUDE_ENG_EST toggle set to True
              (patched in memory), so Engineer's Estimate rows reach the mart.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from bidtab_pipeline.contracts import XLSX_PATH_TABLES

from harness import PIPELINE_NOTEBOOKS, NotebookRun, ReferenceHarness
from snapshot import (
    normalize_dataframe,
    normalize_export_csv,
    normalize_rows,
    schema_of,
    to_json_text,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SOURCE_FIXTURES = FIXTURES / "xlsx_synthetic" / "source_files"
SOURCE_RUN2_OVERRIDES = FIXTURES / "xlsx_synthetic" / "source_files_run2"
CONFIG_FIXTURES = FIXTURES / "config_synthetic"
CONFIG_RUN2_OVERRIDES = FIXTURES / "config_synthetic_run2"
GUARDRAIL_VARIANTS = CONFIG_FIXTURES / "guardrail_variants"

RUN1_EXCLUDE = ("SYN_C.xlsx",)
RUN2_EXCLUDE = ("SYN_B.xlsx",)
EE_INCLUDED_PATCH = {"04_build_mart": [("INCLUDE_ENG_EST = False\n", "INCLUDE_ENG_EST = True\n")]}


def build_volumes(
    dest: Path,
    exclude: tuple[str, ...] = (),
    crosswalk: Path | None = None,
    source_overrides: Path | None = None,
    config_overrides: Path | None = None,
) -> Path:
    """Lay out source_files/ and config/ as the job's volumes; return the volumes root.

    Files in source_overrides and config_overrides replace same-named files.
    """
    source = dest / "source_files"
    source.mkdir(parents=True)
    for entry in SOURCE_FIXTURES.iterdir():
        if entry.name in exclude:
            continue
        if entry.is_dir():
            shutil.copytree(entry, source / entry.name)
        else:
            shutil.copy2(entry, source / entry.name)
    shutil.copytree(CONFIG_FIXTURES, dest / "config", ignore=shutil.ignore_patterns("guardrail_variants"))
    if crosswalk is not None:
        shutil.copy2(crosswalk, dest / "config" / "Final_Recommended_Line_Item_List.csv")
    for overrides, target in ((source_overrides, source), (config_overrides, dest / "config")):
        if overrides is not None:
            for entry in overrides.iterdir():
                shutil.copy2(entry, target / entry.name)
    return dest


@dataclass
class ScenarioOutput:
    name: str
    harness: ReferenceHarness
    runs: dict[str, NotebookRun]
    files: dict[str, str]
    # False when a later scenario reused the database: query `files`, not live tables.
    live: bool = True

    def live_table(self, name: str):
        if not self.live:
            raise RuntimeError(f"{self.name}: database was reused by a later scenario; use captured files")
        return self.harness.table(name)


def capture(harness: ReferenceHarness, runs: dict[str, NotebookRun]) -> dict[str, str]:
    """Normalize everything a run produced into {relative_path: text}."""
    files: dict[str, str] = {}
    schemas = {}
    for table in XLSX_PATH_TABLES:
        df = harness.table(table)
        schemas[table] = schema_of(df)
        files[f"tables/{table}.csv"] = normalize_dataframe(df)
    files["tables/_schema.json"] = to_json_text(schemas)

    exports = harness.volumes_root / "exports"
    if exports.exists():
        for path in sorted(exports.glob("*.csv")):
            files[f"exports/{path.name}"] = normalize_export_csv(path)

    display_schemas = {}
    for name, run in runs.items():
        for d in run.displays:
            # Keyed by display order, not cell index: a port may regroup cells but
            # must show the same results in the same order.
            key = f"{name}/display{d.ordinal:02d}"
            display_schemas[key] = [list(c) for c in d.columns]
            files[f"displays/{key}.csv"] = normalize_rows([c for c, _ in d.columns], d.rows)
        files[f"stdout/{name}.txt"] = mask_stdout(run.stdout, harness)
    files["displays/_schema.json"] = to_json_text(display_schemas)
    return files


def mask_stdout(text: str, harness: ReferenceHarness) -> str:
    text = text.replace(harness.volumes_root.as_posix(), "<VOLUMES>")
    text = text.replace(f"`{harness.db}`", "`<DB>`")
    return re.sub(r"Logged run [0-9a-f]{8}", "Logged run <RUN_ID>", text)


def run_scenarios(
    spark, workdir: Path, db_prefix: str = "ref", refactored: frozenset[str] = frozenset()
) -> dict[str, ScenarioOutput]:
    """Run every scenario. `refactored` names the notebooks to take from notebooks/."""
    out: dict[str, ScenarioOutput] = {}

    def run(harness, patches=None):
        return harness.run_pipeline(PIPELINE_NOTEBOOKS, patches=patches, refactored=refactored)

    vol1 = build_volumes(workdir / "base_run1", exclude=RUN1_EXCLUDE)
    h1 = ReferenceHarness(spark, vol1, f"{db_prefix}_base")
    h1.reset_database()
    runs = run(h1)
    out["base_run1"] = ScenarioOutput("base_run1", h1, runs, capture(h1, runs))

    vol2 = build_volumes(
        workdir / "base_run2",
        exclude=RUN2_EXCLUDE,
        source_overrides=SOURCE_RUN2_OVERRIDES,
        config_overrides=CONFIG_RUN2_OVERRIDES,
    )
    h2 = ReferenceHarness(spark, vol2, f"{db_prefix}_base")  # same database: audit logs accumulate
    runs = run(h2)
    out["base_run2"] = ScenarioOutput("base_run2", h2, runs, capture(h2, runs))
    out["base_run1"].live = False

    vol3 = build_volumes(workdir / "ee_included", exclude=RUN1_EXCLUDE)
    h3 = ReferenceHarness(spark, vol3, f"{db_prefix}_ee_included")
    h3.reset_database()
    runs = run(h3, patches=EE_INCLUDED_PATCH)
    out["ee_included"] = ScenarioOutput("ee_included", h3, runs, capture(h3, runs))
    return out


def run_reference_scenarios(spark, workdir: Path) -> dict[str, ScenarioOutput]:
    return run_scenarios(spark, workdir, "ref")
