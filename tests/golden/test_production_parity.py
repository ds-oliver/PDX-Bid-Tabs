"""Gate 2b: reference and refactored pipelines on the production inputs.

Skipped until the Port's snapshots are in local_inputs/ (gitignored, never
committed). Expected layout:

    local_inputs/volumes/source_files/   top level of /Volumes/pop-poc/bidtab/source_files/
    local_inputs/volumes/config/         /Volumes/pop-poc/bidtab/config/
    local_inputs/fresh_run/exports/      the six 05 CSVs from a fresh job run on those inputs
    local_inputs/golden/golden_run_2026-05-28.json

The volumes are copied to a temp dir first, so the run never writes into
local_inputs/. Checks:
1. Reference and refactored outputs are identical (every table, export,
   display, and printed line), except B-14 on branch fix/b14-bid-date: tables
   and exports may differ only in bid_date and bid_year, and displays only if
   they carry bid_date or bid_year (aggregates grouped by year change shape).
2. Both match the fresh 05 export, row for row, excluding load timestamps.
3. If BIDTAB_INPUTS_MATCH_GOLDEN=1 (the inputs are the 2026-05-28 inputs),
   table counts and per-file mart rows match golden_run_2026-05-28.json.
   Otherwise the differences are printed, not asserted (handoff Phase 2, Gate 2b).
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
from pathlib import Path

import pytest

from harness import PIPELINE_NOTEBOOKS, ReferenceHarness
from scenarios import capture
from snapshot import compare_trees, normalize_export_csv

LOCAL_INPUTS = Path(__file__).resolve().parents[2] / "local_inputs"
VOLUMES = LOCAL_INPUTS / "volumes"
FRESH_EXPORTS = LOCAL_INPUTS / "fresh_run" / "exports"
GOLDEN = LOCAL_INPUTS / "golden" / "golden_run_2026-05-28.json"

pytestmark = [
    pytest.mark.spark,
    pytest.mark.skipif(
        not (VOLUMES / "source_files").is_dir() or not (VOLUMES / "config").is_dir(),
        reason="production inputs not in local_inputs/volumes/ (Gate 2b is blocked on the Port)",
    ),
]


def _run(spark, workdir: Path, db: str, refactored: bool):
    volumes = workdir / db
    shutil.copytree(VOLUMES / "source_files", volumes / "source_files")
    shutil.copytree(VOLUMES / "config", volumes / "config")
    harness = ReferenceHarness(spark, volumes, db)
    harness.reset_database()
    notebooks = frozenset(PIPELINE_NOTEBOOKS) if refactored else frozenset()
    runs = harness.run_pipeline(PIPELINE_NOTEBOOKS, refactored=notebooks)
    return harness, capture(harness, runs)


@pytest.fixture(scope="module")
def production_runs(spark, tmp_path_factory):
    workdir = tmp_path_factory.mktemp("production")
    return {
        "reference": _run(spark, workdir, "prod_ref", refactored=False),
        "refactored": _run(spark, workdir, "prod_rf", refactored=True),
    }


B14_DATE_COLUMNS = ("bid_date", "bid_year")


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _without(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    return sorted(json.dumps({k: v for k, v in r.items() if k not in columns}, sort_keys=True) for r in rows)


def test_refactored_equals_reference(production_runs):
    """Identical except for B-14 (fix/b14-bid-date): bid_date and bid_year, and displays aggregated on them."""
    _, reference = production_runs["reference"]
    _, refactored = production_runs["refactored"]
    problems = []
    for path in sorted(set(reference) | set(refactored)):
        a, b = reference.get(path), refactored.get(path)
        if a == b:
            continue
        if a is None or b is None or not path.endswith(".csv"):
            problems.append(f"{path}: differs outside B-14")
            continue
        ra, rb = _rows(a), _rows(b)
        dates = [c for c in (ra[0] if ra else {}) if c in B14_DATE_COLUMNS]
        if not dates:
            problems.append(f"{path}: differs and has no bid_date/bid_year column")
        elif path.startswith(("tables/", "exports/")):
            if _without(ra, dates) != _without(rb, dates):
                problems.append(f"{path}: rows differ beyond {dates}")
    assert not problems, "\n".join(problems)


@pytest.mark.skipif(not FRESH_EXPORTS.is_dir(), reason="no fresh 05 export in local_inputs/fresh_run/exports/")
@pytest.mark.parametrize("which", ["reference", "refactored"])
def test_matches_fresh_job_export(which, production_runs):
    _, files = production_runs[which]
    expected = {f"exports/{p.name}": normalize_export_csv(p) for p in sorted(FRESH_EXPORTS.glob("*.csv"))}
    actual = {k: v for k, v in files.items() if k.startswith("exports/")}
    problems = compare_trees(expected, actual)
    assert not problems, "\n\n".join(problems)


@pytest.mark.skipif(not GOLDEN.is_file(), reason="no golden_run_2026-05-28.json in local_inputs/golden/")
def test_golden_run_counts(production_runs):
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    harness, files = production_runs["refactored"]

    differences = []
    for table, expected in golden["table_rows"].items():
        if table == "silver_contractor_rows":
            got = harness.spark.sql(
                f"SELECT COUNT(*) FROM `{harness.db}`.`silver_bid_items` WHERE NOT is_engineers_estimate"
            ).collect()[0][0]
        else:
            got = harness.table(table).count()
        if got != expected:
            differences.append(f"{table}: golden {expected}, now {got}")

    mart = list(csv.DictReader(io.StringIO(files["tables/mart_bid_analysis.csv"])))
    for entry in golden["mart_rows_by_file"]:
        got = sum(1 for r in mart if r["source_file"] == entry["source_file"])
        if got != entry["mart_rows"]:
            differences.append(f"{entry['source_file']}: golden {entry['mart_rows']} mart rows, now {got}")

    if os.environ.get("BIDTAB_INPUTS_MATCH_GOLDEN") == "1":
        assert not differences, "\n".join(differences)
    elif differences:
        pytest.skip("inputs differ from 2026-05-28; record these, do not force a match:\n" + "\n".join(differences))
