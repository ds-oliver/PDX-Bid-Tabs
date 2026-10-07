"""Phase 1 gate: the reference notebooks run end to end and match the committed snapshots.

To accept a deliberate change (new fixture, new scenario), regenerate with
`pytest tests/golden --update-snapshots` and review the diff.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import NotebookError, ReferenceHarness
from scenarios import GUARDRAIL_VARIANTS, RUN1_EXCLUDE, build_volumes
from snapshot import compare_trees, read_tree, write_tree

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
SCENARIOS = ("base_run1", "base_run2", "ee_included")

pytestmark = pytest.mark.spark


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_reference_matches_snapshot(scenario, reference_outputs, request):
    actual = reference_outputs[scenario].files
    root = SNAPSHOTS / scenario
    if request.config.getoption("--update-snapshots"):
        write_tree(root, actual)
        pytest.skip(f"snapshot rewritten: {root}")
    assert root.exists(), f"No snapshot at {root}; run with --update-snapshots"
    problems = compare_trees(read_tree(root), actual)
    assert not problems, "\n\n".join(problems)


@pytest.mark.parametrize(
    ("variant", "message"),
    [
        ("missing_column.csv", "Crosswalk source is missing required columns: {'catalog_cost_code_desc'}"),
        ("null_raw.csv", "Crosswalk has NULL item_description_raw rows"),
        ("null_normalized.csv", "Crosswalk has NULL item_description_normalized rows"),
        ("duplicate_key.csv", "Duplicate raw_join_key found (2 rows). Mart join would explode."),
        ("bad_spec_type.csv", "Unrecognized spec_type values: {'STATE'}"),
    ],
)
@pytest.mark.parametrize("refactored", [False, True], ids=["reference", "refactored"])
def test_crosswalk_guardrail_halts(variant, message, refactored, spark, tmp_path):
    """03 hard-fails on each crosswalk defect it checks for (FR-30 guardrails), before and after the port."""
    volumes = build_volumes(tmp_path / "volumes", exclude=RUN1_EXCLUDE, crosswalk=GUARDRAIL_VARIANTS / variant)
    prefix = "rf" if refactored else "ref"
    harness = ReferenceHarness(spark, volumes, f"{prefix}_guardrail_{Path(variant).stem}")
    harness.reset_database()
    with pytest.raises(NotebookError) as info:
        harness.run_notebook("03_load_crosswalk", refactored=refactored)
    assert isinstance(info.value.cause, AssertionError)
    assert message in str(info.value.cause)
    assert not spark.catalog.tableExists(f"{harness.db}.int_crosswalk"), "03 must halt before writing int_crosswalk"
