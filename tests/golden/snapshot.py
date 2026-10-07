"""Normalize pipeline outputs into deterministic text files.

The same normalization serves two purposes:
- Snapshots of the reference notebooks on synthetic inputs (Phase 1 gate).
- Equivalence of refactored and reference outputs (Phase 2): "row-level
  equality after sorting, excluding *_loaded_at timestamps".

Normalization rules:
- Volatile columns (load timestamps, run ids, run timestamps) are dropped from
  values. Table schemas still list them.
- Values are rendered exactly: None as <null>, floats with repr(), dates ISO.
- Arrays are sorted, because COLLECT_SET order is not deterministic.
- Rows are sorted.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame

VOLATILE_COLUMNS = frozenset(
    {
        "bronze_loaded_at",
        "silver_loaded_at",
        "mart_loaded_at",
        "report_generated_at",
        "run_id",
        "run_timestamp",
        "last_mart_build",
    }
)
NULL = "<null>"
_NUMPY_ARRAY_REPR = re.compile(r"^\[(?:'[^']*'\s*)*\]$")


def fmt(value: Any) -> str:
    if value is None:
        return NULL
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.datetime | dt.date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return "[" + ", ".join(sorted(fmt(v) for v in value)) + "]"
    if hasattr(value, "item") and not isinstance(value, str):  # numpy scalar
        return fmt(value.item())
    return str(value)


def to_csv_text(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def normalize_rows(columns: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    keep = [i for i, c in enumerate(columns) if c not in VOLATILE_COLUMNS]
    header = [columns[i] for i in keep]
    body = sorted(tuple(fmt(row[i]) for i in keep) for row in rows)
    return to_csv_text(header, body)


def normalize_dataframe(df: DataFrame) -> str:
    return normalize_rows(df.columns, (tuple(r) for r in df.collect()))


def schema_of(df: DataFrame) -> list[list[str]]:
    return [[f.name, f.dataType.simpleString()] for f in df.schema.fields]


def normalize_export_csv(path: Path) -> str:
    """Normalize a CSV written by 05 (pandas to_csv). Values stay as pandas wrote them."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        rows = list(reader)
    keep = [i for i, c in enumerate(header) if c not in VOLATILE_COLUMNS]

    def cell(v: str) -> str:
        # COLLECT_SET arrays arrive as numpy reprs, e.g. "['A' 'B']"; sort elements.
        if _NUMPY_ARRAY_REPR.match(v):
            return "[" + " ".join(sorted(re.findall(r"'[^']*'", v))) + "]"
        return v

    body = sorted(tuple(cell(row[i]) for i in keep) for row in rows)
    return to_csv_text([header[i] for i in keep], body)


def to_json_text(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True) + "\n"


def compare_trees(expected: dict[str, str], actual: dict[str, str]) -> list[str]:
    """Return human-readable differences between two {relative_path: text} maps."""
    import difflib

    problems = []
    for path in sorted(set(expected) - set(actual)):
        problems.append(f"missing from actual: {path}")
    for path in sorted(set(actual) - set(expected)):
        problems.append(f"unexpected in actual: {path}")
    for path in sorted(set(expected) & set(actual)):
        if expected[path] != actual[path]:
            diff = difflib.unified_diff(
                expected[path].splitlines(),
                actual[path].splitlines(),
                "expected/" + path,
                "actual/" + path,
                lineterm="",
            )
            problems.append("\n".join(list(diff)[:40]))
    return problems


def read_tree(root: Path) -> dict[str, str]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in files}


def write_tree(root: Path, files: dict[str, str]) -> None:
    import shutil

    if root.exists():
        shutil.rmtree(root)
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
