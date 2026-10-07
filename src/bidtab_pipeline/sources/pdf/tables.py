"""Ruled-table extraction and cell text helpers.

Compiled bid tabs are Excel sheets printed with cell borders, so pdfplumber's
line-based table finder recovers the grid: one table per page, wrapped text
kept inside its cell, amounts in their own column. Column assignment comes from
the ruling, not from guessing x positions.
"""

from __future__ import annotations

import re

from bidtab_pipeline.sources.pdf.model import LayoutFlag

TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
_WS = re.compile(r"\s+")


def page_table(page, page_no: int) -> list[list[str | None]]:
    tables = page.extract_tables(TABLE_SETTINGS)
    if len(tables) != 1:
        raise LayoutFlag("table_count", f"expected one ruled table, found {len(tables)}", page_no)
    return tables[0]


def cell_lines(cell: str | None) -> list[str]:
    """Non-empty lines of a cell, each with single spaces."""
    return [_WS.sub(" ", ln).strip() for ln in (cell or "").split("\n") if ln.strip()]


def one_line(cell: str | None) -> str:
    """A cell's text with wrapped lines joined by single spaces."""
    return " ".join(cell_lines(cell))
