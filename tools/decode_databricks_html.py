#!/usr/bin/env python3
"""Decode Databricks notebook HTML exports to Databricks .py source format.

Databricks HTML exports embed the notebook as base64(urlencode(json)) in
`__DATABRICKS_NOTEBOOK_MODEL`. This script rebuilds the `.py` source export
format: header line, cells joined by the COMMAND separator, magic cells
prefixed with `# MAGIC`, and no trailing newline.

Verified 2026-10-06: decoding `Src Build (final)` HTML reproduces the native
`Src Build (final2)` .py export byte-for-byte for 01, 03, 04. For 02 the only
difference is one trailing empty cell the HTML export omits.

Usage:
    python tools/decode_databricks_html.py --verify     # decode the 2026-05-28 baseline, check hashes
    python tools/decode_databricks_html.py IN.html OUT.py
"""
import base64
import hashlib
import json
import re
import sys
import urllib.parse
from pathlib import Path

SEP = "\n\n# COMMAND ----------\n\n"
DL = Path.home() / "Downloads"

# Baseline: job run of bidtab_pipeline_full_refresh, 2026-05-28 21:07-21:11 UTC.
BASELINE = {
    "01_parse_single_bidtab.py": (DL / "notebook01_bronze_pipeline_run.html",
        "7325468ad7666dfe30d82c08eaba2403da21f211f2af0e1bd3ac8529e0c3c63d"),
    "02_build_silver.py": (DL / "notebook02_silver_pipeline_run.html",
        "02fcc89aee45d1f72067f72da20356b55a80ba75b39780ead7bb9cdca0fc67b6"),
    "03_load_crosswalk.py": (DL / "notebook03_load_xwalk_pipeline_run.html",
        "13ec6ef53a2d304417750829c6d20a60d59ea5cbd67697387b6d795d7f4d99bc"),
    # The 2026-05-28 run's own 04 export. notebook04_build_mart_pipeline_run_20260603.html
    # is a later run (2026-05-30 01:09 UTC) that decodes to the same source hash.
    "04_build_mart.py": (DL / "notebook04_build_mart_pipeline_run.html",
        "e438855f21474b4f87f1ee323345ab408637729a3c0d87a9ff5aa3fb84ff91cd"),
    "05_export_csvs.py": (DL / "notebook05_export_csvs_pipeline_run.html",
        "913702df8d454e39d40c39dd9c6c2eb236e1d7ae188e496abb093b45442de62e"),
    "README.py": (DL / "Src (final3)" / "README.html",
        "9a43e91cd8003fafbbee6eac49b94bd29015a58a7b36157827d913d269b331a5"),
}


def load_model(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"__DATABRICKS_NOTEBOOK_MODEL = '([^']+)'", text)
    if not m:
        raise ValueError(f"No notebook model in {path}")
    return json.loads(urllib.parse.unquote(base64.b64decode(m.group(1)).decode("utf-8")))


def to_source(model: dict) -> str:
    cells = []
    for cmd in sorted(model.get("commands", []), key=lambda c: c.get("position", 0)):
        body = cmd.get("command", "")
        if body.lstrip().startswith("%"):
            body = "\n".join(("# MAGIC " + ln) if ln else "# MAGIC" for ln in body.split("\n"))
        cells.append(body)
    return "# Databricks notebook source\n" + SEP.join(cells)


def decode(src: Path, dst: Path) -> str:
    out = to_source(load_model(src))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding="utf-8")
    return hashlib.sha256(out.encode("utf-8")).hexdigest()


def main() -> int:
    if len(sys.argv) == 3:
        print(decode(Path(sys.argv[1]), Path(sys.argv[2])))
        return 0
    if sys.argv[1:] == ["--verify"]:
        outdir = Path("reference/databricks_2026-05-28/notebooks")
        failed = 0
        for name, (src, expected) in BASELINE.items():
            got = decode(src, outdir / name)
            ok = got == expected
            failed += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {name} {got}")
        return 1 if failed else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
