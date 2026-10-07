"""Code copied verbatim from the reference notebooks must stay byte-identical.

Each entry maps a package module to the reference notebook lines it copies. A
failure means someone edited ported baseline logic: that is a behavior change
and needs a backlog entry and a Port decision, not a quiet edit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "reference" / "databricks_2026-05-28" / "notebooks"

# (package file, first line of the copy in that file, reference notebook, first and last reference line)
VERBATIM = [
    ("src/bidtab_pipeline/sources/xlsx/parser.py", 19, "01_parse_single_bidtab.py", 47, 410),
]


@pytest.mark.parametrize(("module", "start", "notebook", "ref_first", "ref_last"), VERBATIM)
def test_copy_is_verbatim(module, start, notebook, ref_first, ref_last):
    ref_lines = (REFERENCE / notebook).read_text(encoding="utf-8").split("\n")[ref_first - 1 : ref_last]
    mod_lines = (REPO / module).read_text(encoding="utf-8").split("\n")[start - 1 :]
    assert mod_lines[: len(ref_lines)] == ref_lines
    assert not "".join(mod_lines[len(ref_lines) :]).strip(), "unexpected code after the verbatim copy"
