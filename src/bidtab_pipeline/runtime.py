"""Resolve Databricks runtime objects (spark, dbutils, display) with local fallbacks.

Package functions never reference notebook globals: they take `spark` and an
optional `dbutils` as arguments. Notebooks pass the objects Databricks injects.
Other callers (local scripts, the PDF CLI) use these helpers:

- get_spark(): the active session on Databricks; otherwise the local backend
  in bidtab_pipeline.io.local_spark (needs the `local` extra).
- get_dbutils(spark): Databricks DBUtils when available, else None. Functions
  that take dbutils fall back to the local filesystem on None.
- get_display(): the notebook's display() when running in one, else a fallback
  that prints the DataFrame.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def get_spark(local_warehouse: str | Path = "spark-warehouse"):
    from pyspark.sql import SparkSession

    active = SparkSession.getActiveSession()
    if active is not None:
        return active
    from bidtab_pipeline.io.local_spark import get_local_spark

    return get_local_spark(local_warehouse)


def get_dbutils(spark: Any = None) -> Any:
    try:
        from pyspark.dbutils import DBUtils  # only present on Databricks
    except ImportError:
        return _from_notebook_namespace("dbutils")
    return DBUtils(spark)


def get_display():
    display = _from_notebook_namespace("display")
    return display if display is not None else _print_display


def _print_display(obj: Any) -> None:
    show = getattr(obj, "show", None)
    if callable(show):
        show(truncate=False)
    else:
        print(obj)


def _from_notebook_namespace(name: str) -> Any:
    try:
        from IPython import get_ipython
    except ImportError:
        return None
    shell = get_ipython()
    return None if shell is None else shell.user_ns.get(name)
