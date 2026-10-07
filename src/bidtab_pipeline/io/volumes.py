"""Volume access that works on Databricks (dbutils) and locally (filesystem)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def list_entry_names(path: str, dbutils: Any = None) -> list[str]:
    """Names of the entries in a directory. Directory names end with '/', as dbutils.fs.ls reports them."""
    if dbutils is not None:
        return [str(info.name) for info in dbutils.fs.ls(path)]
    return [p.name + ("/" if p.is_dir() else "") for p in sorted(Path(path).iterdir())]


def make_dirs(path: str, dbutils: Any = None) -> None:
    if dbutils is not None:
        dbutils.fs.mkdirs(path)
    else:
        Path(path).mkdir(parents=True, exist_ok=True)
