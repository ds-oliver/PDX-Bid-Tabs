"""Differential harness: run the unchanged 2026-05-28 reference notebooks locally.

Each reference notebook (`reference/databricks_2026-05-28/notebooks/*.py`) is
split on the Databricks COMMAND separator and its cells are executed in order
with a local `spark`, a `dbutils` shim, and a capturing `display`. The files on
disk are never modified; these rewrites happen in memory only:

- Table names: `` `pop-poc`.`bidtab`.<table> `` becomes `` `<db>`.<table> ``.
- Volume paths: a string literal that starts with ``/Volumes/pop-poc/bidtab/``
  points at ``<volumes_root>/`` instead. Paths in the middle of a string are
  left alone: 04 writes one into the `suggested_action` text that staff read,
  and that text is data.
- ``%sql`` cells run each statement through ``spark.sql`` and display the last
  result, as Databricks does. ``%md`` cells are skipped.

This produces reference outputs for any input set with no Databricks access.
"""

from __future__ import annotations

import contextlib
import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pyspark.sql import DataFrame, SparkSession

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DIR = REPO_ROOT / "reference" / "databricks_2026-05-28" / "notebooks"

PIPELINE_NOTEBOOKS = (
    "01_parse_single_bidtab",
    "02_build_silver",
    "03_load_crosswalk",
    "04_build_mart",
    "05_export_csvs",
)

NOTEBOOK_HEADER = "# Databricks notebook source\n"
CELL_SEPARATOR = "\n\n# COMMAND ----------\n\n"
PROD_TABLE_PREFIX = "`pop-poc`.`bidtab`."
PROD_VOLUME_ROOT = "/Volumes/pop-poc/bidtab/"
_VOLUME_LITERAL_RE = re.compile(r"(?<=[\"'])" + re.escape(PROD_VOLUME_ROOT))

# Production paths that must survive the rewrite because they are data, not I/O.
# Keyed by notebook; value is the expected count of untouched occurrences.
EXPECTED_UNREWRITTEN_PATHS = {"04_build_mart": 1}


class NotebookError(RuntimeError):
    """A reference notebook cell raised. Carries the cell and captured stdout."""

    def __init__(self, notebook: str, cell_index: int, cell_source: str, stdout: str, cause: BaseException):
        self.notebook = notebook
        self.cell_index = cell_index
        self.cell_source = cell_source
        self.stdout = stdout
        self.cause = cause
        head = "\n".join(cell_source.splitlines()[:5])
        super().__init__(
            f"{notebook} cell {cell_index} raised {type(cause).__name__}: {cause}\n--- cell head ---\n{head}"
        )


@dataclass(frozen=True)
class Cell:
    index: int
    kind: str  # "python", "sql", or "md"
    source: str


@dataclass
class Captured:
    """A materialized display() result. Rows are collected when display() runs."""

    notebook: str
    cell_index: int
    ordinal: int
    columns: list[tuple[str, str]]
    rows: list[tuple[Any, ...]]


@dataclass
class NotebookRun:
    name: str
    displays: list[Captured] = field(default_factory=list)
    stdout: str = ""


@dataclass(frozen=True)
class FileInfo:
    """Shape of the objects `dbutils.fs.ls` returns."""

    path: str
    name: str
    size: int
    modificationTime: int


class _FsShim:
    def ls(self, path: str) -> list[FileInfo]:
        root = Path(path)
        if not root.is_dir():
            raise FileNotFoundError(f"dbutils shim: {path} is not a directory")
        out = []
        for child in sorted(root.iterdir()):
            suffix = "/" if child.is_dir() else ""
            stat = child.stat()
            out.append(
                FileInfo(
                    path=str(child) + suffix,
                    name=child.name + suffix,
                    size=0 if child.is_dir() else stat.st_size,
                    modificationTime=int(stat.st_mtime * 1000),
                )
            )
        return out

    def mkdirs(self, path: str) -> bool:
        Path(path).mkdir(parents=True, exist_ok=True)
        return True


class DbutilsShim:
    """Only the dbutils calls the reference notebooks make (fs.ls, fs.mkdirs)."""

    def __init__(self) -> None:
        self.fs = _FsShim()


def _strip_magic_prefix(line: str) -> str:
    for prefix in ("# MAGIC ", "# MAGIC"):
        if line.startswith(prefix):
            return line[len(prefix) :]
    return line


def parse_cells(text: str) -> list[Cell]:
    if not text.startswith(NOTEBOOK_HEADER):
        raise ValueError("Not a Databricks .py notebook export (missing header line)")
    cells = []
    for i, raw in enumerate(text[len(NOTEBOOK_HEADER) :].split(CELL_SEPARATOR)):
        lines = raw.split("\n")
        content = [ln for ln in lines if ln.strip()]
        if content and all(ln.startswith("# MAGIC") for ln in content):
            body = "\n".join(_strip_magic_prefix(ln) for ln in lines)
            magic, _, rest = body.lstrip().partition("\n")
            magic = magic.strip()
            if magic == "%sql":
                cells.append(Cell(i, "sql", rest))
            elif magic == "%md":
                cells.append(Cell(i, "md", rest))
            else:
                raise ValueError(f"Unsupported magic in cell {i}: {magic!r}")
        else:
            cells.append(Cell(i, "python", raw))
    return cells


def split_sql_statements(sql: str) -> list[str]:
    """Split a %sql cell on semicolons. Reference cells have none inside literals."""
    statements = []
    for chunk in sql.split(";"):
        meaningful = [ln for ln in chunk.splitlines() if ln.strip() and not ln.strip().startswith("--")]
        if meaningful:
            statements.append(chunk.strip())
    return statements


class ReferenceHarness:
    """Runs reference notebooks against a local database and volume root."""

    def __init__(
        self,
        spark: SparkSession,
        volumes_root: Path,
        db: str,
        reference_dir: Path = REFERENCE_DIR,
    ) -> None:
        self.spark = spark
        self.volumes_root = Path(volumes_root).resolve()
        self.db = db
        self.reference_dir = reference_dir
        self.dbutils = DbutilsShim()

    # --- setup -------------------------------------------------------------

    def reset_database(self) -> None:
        self.spark.sql(f"DROP DATABASE IF EXISTS `{self.db}` CASCADE")
        self.spark.sql(f"CREATE DATABASE `{self.db}`")

    # --- source loading and in-memory rewrite -------------------------------

    def load_source(self, notebook: str, patches: list[tuple[str, str]] | None = None) -> str:
        text = (self.reference_dir / f"{notebook}.py").read_text(encoding="utf-8")
        for old, new in patches or []:
            count = text.count(old)
            if count != 1:
                raise ValueError(f"Patch for {notebook} must match exactly once, matched {count}: {old!r}")
            text = text.replace(old, new)
        return self.rewrite(notebook, text)

    def rewrite(self, notebook: str, text: str) -> str:
        text = text.replace(PROD_TABLE_PREFIX, f"`{self.db}`.")
        text = _VOLUME_LITERAL_RE.sub(self.volumes_root.as_posix() + "/", text)
        leftover = text.count(PROD_VOLUME_ROOT)
        expected = EXPECTED_UNREWRITTEN_PATHS.get(notebook, 0)
        if leftover != expected:
            raise ValueError(
                f"{notebook}: {leftover} production volume paths left after rewrite, expected {expected}. "
                "The reference code changed shape; review the rewrite rules."
            )
        if "pop-poc" in text.replace(PROD_VOLUME_ROOT, ""):
            raise ValueError(f"{notebook}: unrewritten `pop-poc` reference outside a known data literal")
        return text

    # --- execution -----------------------------------------------------------

    def run_notebook(self, notebook: str, patches: list[tuple[str, str]] | None = None) -> NotebookRun:
        run = NotebookRun(name=notebook)
        cells = parse_cells(self.load_source(notebook, patches))
        current_cell = {"index": -1}
        ordinal = {"n": 0}

        def display(obj: Any) -> None:
            run.displays.append(self._capture(notebook, current_cell["index"], ordinal["n"], obj))
            ordinal["n"] += 1

        namespace: dict[str, Any] = {
            "__name__": "__main__",
            "spark": self.spark,
            "dbutils": self.dbutils,
            "display": display,
        }
        buffer = io.StringIO()
        for cell in cells:
            current_cell["index"] = cell.index
            try:
                with contextlib.redirect_stdout(buffer):
                    if cell.kind == "python":
                        code = compile(cell.source, f"<{notebook} cell {cell.index}>", "exec")
                        exec(code, namespace)  # noqa: S102 - executing the reference notebook is the point
                    elif cell.kind == "sql":
                        result = None
                        for statement in split_sql_statements(cell.source):
                            result = self.spark.sql(statement)
                        if result is not None:
                            display(result)
            except Exception as exc:
                run.stdout = buffer.getvalue()
                raise NotebookError(notebook, cell.index, cell.source, run.stdout, exc) from exc
        run.stdout = buffer.getvalue()
        return run

    def run_pipeline(
        self,
        notebooks: tuple[str, ...] = PIPELINE_NOTEBOOKS,
        patches: dict[str, list[tuple[str, str]]] | None = None,
    ) -> dict[str, NotebookRun]:
        runs = {}
        for notebook in notebooks:
            runs[notebook] = self.run_notebook(notebook, (patches or {}).get(notebook))
            # current_timestamp() must advance between runs for 04's Delta report,
            # which orders runs by run_timestamp.
            time.sleep(0.01)
        return runs

    # --- helpers -------------------------------------------------------------

    def _capture(self, notebook: str, cell_index: int, ordinal: int, obj: Any) -> Captured:
        if isinstance(obj, DataFrame):
            columns = [(f.name, f.dataType.simpleString()) for f in obj.schema.fields]
            rows = [tuple(r) for r in obj.collect()]
        else:
            import pandas as pd

            if not isinstance(obj, pd.DataFrame):
                raise TypeError(f"display() got unsupported type {type(obj).__name__}")
            columns = [(c, str(t)) for c, t in obj.dtypes.items()]
            rows = [tuple(r) for r in obj.itertuples(index=False)]
        return Captured(notebook, cell_index, ordinal, columns, rows)

    def table(self, name: str) -> DataFrame:
        return self.spark.table(f"`{self.db}`.`{name}`")
