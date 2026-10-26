#!/usr/bin/env python3
"""Write copies of the reference notebooks that target an isolated schema and volume (Gate 2c).

The reference notebooks hard-code `pop-poc`.`bidtab` and /Volumes/pop-poc/bidtab/,
so running them as-is would overwrite production. This applies the same rewrite
rules as the local harness (tests/golden/harness.py) and writes .py notebook
sources to upload to a workspace folder. The committed reference files are not
changed, and the output must not be committed.

Usage (from the repo root):
    python tools/make_isolated_reference.py \\
        --table-prefix '`pop-poc`.`bidtab_gate2c_ref`' \\
        --volume-root /Volumes/pop-poc/bidtab_gate2c/ref \\
        --out build/isolated_reference
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests" / "golden"))

from harness import (  # noqa: E402
    _VOLUME_LITERAL_RE,
    EXPECTED_UNREWRITTEN_PATHS,
    PIPELINE_NOTEBOOKS,
    PROD_TABLE_PREFIX,
    PROD_VOLUME_ROOT,
    REFERENCE_DIR,
)


def rewrite(notebook: str, text: str, table_prefix: str, volume_root: str) -> str:
    if table_prefix.replace("`", "").lower() == "pop-poc.bidtab":
        raise SystemExit("--table-prefix must not be the production schema")
    if volume_root.rstrip("/") == PROD_VOLUME_ROOT.rstrip("/"):
        raise SystemExit("--volume-root must not be the production volume root")
    text = text.replace(PROD_TABLE_PREFIX, table_prefix.rstrip(".") + ".")
    text = _VOLUME_LITERAL_RE.sub(volume_root.rstrip("/") + "/", text)
    leftover = text.count(PROD_VOLUME_ROOT)
    if leftover != EXPECTED_UNREWRITTEN_PATHS.get(notebook, 0):
        raise SystemExit(f"{notebook}: unexpected production paths left after rewrite ({leftover})")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--table-prefix", required=True, help="quoted, e.g. `pop-poc`.`bidtab_gate2c_ref`")
    parser.add_argument("--volume-root", required=True, help="isolated volume root holding source_files/ and config/")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for notebook in PIPELINE_NOTEBOOKS:
        text = (REFERENCE_DIR / f"{notebook}.py").read_text(encoding="utf-8")
        (args.out / f"{notebook}.py").write_text(
            rewrite(notebook, text, args.table_prefix, args.volume_root), encoding="utf-8"
        )
        print(f"wrote {args.out / notebook}.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
