"""Ruled-table extraction and cell text helpers.

Compiled bid tabs are Excel sheets printed with cell borders, so pdfplumber's
line-based table finder recovers the grid: one table per page, wrapped text
kept inside its cell, amounts in their own column. Column assignment comes from
the ruling, not from guessing x positions.

Overflow text. When a description has more lines than its row height, Excel
draws the extra line below the cell. The renderer clips it, so it is invisible
on the page, but the text layer keeps it, sitting about one point above the
next row's first line. pdfplumber then merges the two into one garbled line
(2025-12566 item 0057: "A(Sdejucstito En x3is4t4in3g0 0T)axiway ..."). Such a
line is moved back to the cell above only when the evidence is exact: it is in
the description column, and its top equals the cell above's last line top plus
that cell's line pitch (within 0.6 pt). Each repair is a warning. Any other
overlapping text is flagged.
"""

from __future__ import annotations

import re

from pdfplumber.utils import extract_text

from bidtab_pipeline.sources.pdf.model import LayoutFlag

TABLE_SETTINGS = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
DESCRIPTION_COLUMN = 1
_WS = re.compile(r"\s+")
_SAME_LINE = 0.3  # pt: characters of one printed line share a top to well within this
_MERGED_BY_PDFPLUMBER = 3.0  # pt: pdfplumber's line tolerance; distinct lines closer than this get merged
_PITCH_MATCH = 0.6  # pt


def _lines(chars: list[dict]) -> list[tuple[float, list[dict]]]:
    """Group characters into printed lines by their exact top."""
    lines: list[tuple[float, list[dict]]] = []
    for c in sorted(chars, key=lambda c: c["top"]):
        if lines and abs(lines[-1][0] - c["top"]) <= _SAME_LINE:
            lines[-1][1].append(c)
        else:
            lines.append((c["top"], [c]))
    return lines


def _cell_chars(page, bbox, with_spaces: bool = False) -> list[dict]:
    """Characters whose centre lies in the cell (same assignment as cropping, without a crop per cell)."""
    x0, top, x1, bottom = bbox
    return [
        c
        for c in page.chars
        if (with_spaces or c["text"].strip())
        and x0 <= (c["x0"] + c["x1"]) / 2 <= x1
        and top <= (c["top"] + c["bottom"]) / 2 <= bottom
    ]


def _text(chars: list[dict]) -> str:
    """Rebuild text from characters, keeping the text layer's own space glyphs."""
    return extract_text(sorted(chars, key=lambda ch: (round(ch["top"], 1), ch["x0"])), keep_blank_chars=True)


def page_table(page, page_no: int) -> tuple[list[list[str | None]], list[str]]:
    """The page's one ruled table as cell text, and warnings for repaired overflow lines."""
    tables = page.find_tables(TABLE_SETTINGS)
    if len(tables) != 1:
        raise LayoutFlag("table_count", f"expected one ruled table, found {len(tables)}", page_no)
    table = tables[0]
    text = table.extract()
    warnings: list[str] = []
    for r, row in enumerate(table.rows):
        for c, bbox in enumerate(row.cells):
            if bbox is None:
                continue
            lines = _lines(_cell_chars(page, bbox))
            clashes = [(a, b) for a, b in zip(lines, lines[1:], strict=False) if b[0] - a[0] < _MERGED_BY_PDFPLUMBER]
            if not clashes:
                continue
            overflow = _overflow_line(page, table, r, c, clashes)
            if overflow is None:
                raise LayoutFlag(
                    "overlapping_text",
                    f"row {r + 1}, column {c + 1}: text lines {[round(t, 1) for t, _ in lines]} overlap",
                    page_no,
                )
            spaced = _lines(_cell_chars(page, bbox, with_spaces=True))
            own = [ch for top, chs in spaced if abs(top - overflow[0]) > _SAME_LINE for ch in chs]
            moved = _WS.sub(
                " ", _text([ch for top, chs in spaced if abs(top - overflow[0]) <= _SAME_LINE for ch in chs])
            ).strip()
            text[r][c] = _text(own)
            text[r - 1][c] = (text[r - 1][c] or "") + "\n" + moved
            warnings.append(f"overflow_text_reassigned: page {page_no}, {moved!r} moved to the row above")
    return text, warnings


def _overflow_line(page, table, r: int, c: int, clashes) -> tuple[float, list[dict]] | None:
    """The clashing line that continues the cell above at its line pitch, or None."""
    if c != DESCRIPTION_COLUMN or r == 0 or len(clashes) != 1:
        return None
    above_bbox = table.rows[r - 1].cells[c]
    if above_bbox is None:
        return None
    above = _lines(_cell_chars(page, above_bbox))
    if len(above) < 2:
        return None
    expected = above[-1][0] + (above[-1][0] - above[-2][0])
    a, b = clashes[0]
    matches = [line for line in (a, b) if abs(line[0] - expected) <= _PITCH_MATCH]
    return matches[0] if len(matches) == 1 else None


def cell_lines(cell: str | None) -> list[str]:
    """Non-empty lines of a cell, each with single spaces."""
    return [_WS.sub(" ", ln).strip() for ln in (cell or "").split("\n") if ln.strip()]


def one_line(cell: str | None) -> str:
    """A cell's text with wrapped lines joined by single spaces."""
    return " ".join(cell_lines(cell))
