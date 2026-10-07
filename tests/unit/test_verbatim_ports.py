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

# (package file, first line of the copy, indent added in the package, reference notebook, first and last line)
VERBATIM = [
    ("src/bidtab_pipeline/sources/xlsx/parser.py", 19, 0, "01_parse_single_bidtab.py", 47, 410),
    ("src/bidtab_pipeline/config_loader/crosswalk.py", 21, 4, "03_load_crosswalk.py", 16, 114),
]


def _dedent(line: str, indent: int) -> str:
    if not line:
        return line
    assert line.startswith(" " * indent), f"line lost its indent: {line!r}"
    return line[indent:]


@pytest.mark.parametrize(("module", "start", "indent", "notebook", "ref_first", "ref_last"), VERBATIM)
def test_copy_is_verbatim(module, start, indent, notebook, ref_first, ref_last):
    ref_lines = (REFERENCE / notebook).read_text(encoding="utf-8").split("\n")[ref_first - 1 : ref_last]
    mod_lines = (REPO / module).read_text(encoding="utf-8").split("\n")[start - 1 : start - 1 + len(ref_lines)]
    assert [_dedent(ln, indent) for ln in mod_lines] == ref_lines
