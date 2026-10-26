#!/usr/bin/env python3
"""Compare two directories of 05 CSV exports with the parity normalization (Gate 2c).

Uses the same rules as the local snapshot and equivalence tests
(tests/golden/snapshot.py): load timestamps and run ids excluded, COLLECT_SET
arrays sorted, rows sorted. Exit status 0 means identical.

Usage (from the repo root):
    python tools/compare_exports.py EXPECTED_DIR ACTUAL_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests" / "golden"))

from snapshot import compare_trees, normalize_export_csv  # noqa: E402


def load(directory: Path) -> dict[str, str]:
    return {p.name: normalize_export_csv(p) for p in sorted(directory.glob("*.csv"))}


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    expected, actual = (Path(a) for a in sys.argv[1:])
    problems = compare_trees(load(expected), load(actual))
    if problems:
        print("\n\n".join(problems))
        print(f"\n{len(problems)} difference(s)")
        return 1
    print(f"identical: {len(load(expected))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
