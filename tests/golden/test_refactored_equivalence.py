"""Phase 2 gate 2a: refactored notebooks reproduce the reference outputs exactly.

Every scenario runs with the ported notebooks from notebooks/ and the rest from
reference/. The full capture (tables, exports, displays, stdout) must equal the
reference snapshots. Add each notebook to PORTED as it is ported.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scenarios import run_scenarios
from snapshot import compare_trees, read_tree

SNAPSHOTS = Path(__file__).resolve().parent / "snapshots"
PORTED = frozenset({"01_parse_single_bidtab", "03_load_crosswalk"})

pytestmark = pytest.mark.spark


@pytest.fixture(scope="session")
def refactored_outputs(spark, tmp_path_factory):
    return run_scenarios(spark, tmp_path_factory.mktemp("refactored_volumes"), "rf", refactored=PORTED)


@pytest.mark.parametrize("scenario", ("base_run1", "base_run2", "ee_included"))
def test_refactored_matches_reference(scenario, refactored_outputs):
    problems = compare_trees(read_tree(SNAPSHOTS / scenario), refactored_outputs[scenario].files)
    assert not problems, "\n\n".join(problems)
