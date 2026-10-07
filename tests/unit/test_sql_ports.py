"""SQL ported from the reference notebooks must be the same text at runtime.

Each reference cell is executed against a recording stand-in for `spark`, so
the comparison is on the SQL Spark would receive, after Python string escapes
and f-string substitution. Table names are normalized on both sides.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bidtab_pipeline.settings import Settings
from bidtab_pipeline.transforms import silver

REFERENCE = Path(__file__).resolve().parents[2] / "reference" / "databricks_2026-05-28" / "notebooks"
SEPARATOR = "\n\n# COMMAND ----------\n\n"
PROD = Settings()


class RecordingSpark:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def sql(self, statement: str):
        self.statements.append(statement)
        return statement


def reference_statements(notebook: str, cells: range) -> list[str]:
    """Run reference cells with spark recorded and display() a no-op; %sql cells yield their text."""
    text = (REFERENCE / notebook).read_text(encoding="utf-8")
    all_cells = text.split(SEPARATOR)
    spark = RecordingSpark()
    namespace = {"spark": spark, "display": lambda _: None}
    exec(all_cells[1], namespace)  # constants cell (table names)
    for i in cells:
        cell = all_cells[i]
        if cell.startswith("# MAGIC %sql"):
            lines = cell.split("\n")[1:]
            spark.statements.append(
                "\n".join(ln[8:] if ln.startswith("# MAGIC ") else ln[7:] for ln in lines).strip("\n")
            )
        else:
            exec(cell, namespace)
    return spark.statements


def test_silver_build_sql_is_unchanged():
    expected = reference_statements("02_build_silver.py", range(6, 7))
    got = silver.SILVER_SQL_TEMPLATE.format(
        BRONZE_TABLE=PROD.table("bronze_raw_rows"), SILVER_TABLE=PROD.table("silver_bid_items")
    )
    assert expected == [got]


def test_silver_check_sql_is_unchanged():
    expected = reference_statements("02_build_silver.py", range(7, 20))
    got = [q.format(SILVER_TABLE=PROD.table("silver_bid_items")) for q in silver.SILVER_CHECKS]
    assert [e.strip() for e in expected] == [g.strip() for g in got]


@pytest.mark.parametrize("name", ["bronze_raw_rows", "silver_bid_items"])
def test_production_settings_reproduce_reference_table_names(name):
    assert PROD.table(name) == f"`pop-poc`.`bidtab`.`{name}`"
