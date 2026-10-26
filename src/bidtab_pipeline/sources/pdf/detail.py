"""Detail pages (FR-12 to FR-14): one row per item, prices per bidder column.

Table layout, checked on every page:

    row 0   header block | (blank x3) | bidder 1 | (merged) | bidder 2 | (merged) | ...
    row 1   Item No. | Item Description | Estimated Quantity | Units | Unit Price | Total Price | ...
    rows    0001 | description, wrapped, spec reference on its own line | qty | unit | prices ...
            (blank) | Total Amount <schedule> | | | | total | | total ...

Descriptions are rebuilt in the crosswalk key format (FR-13): wrapped lines
joined with single spaces, spec reference included, as the workbook cells read
after 01's whitespace cleanup. Anything else is flagged, not guessed.
"""

from __future__ import annotations

import re

from bidtab_pipeline.sources.pdf.header import parse_header_block
from bidtab_pipeline.sources.pdf.model import DetailPage, ItemLine, LayoutFlag, TotalLine
from bidtab_pipeline.sources.pdf.tables import cell_lines, one_line

BASE_COLUMNS = ["Item No.", "Item Description", "Estimated Quantity", "Units"]
PRICE_COLUMNS = ["Unit Price", "Total Price"]

_ITEM_NO = re.compile(r"\d{4}")
_AMOUNT = re.compile(r"\$?(\d{1,3}(?:,\d{3})*|\d+)(\.\d+)?")
_SPEC_LINE = re.compile(r"\(((?:Section|Item)\s+[^()]+)\)")
# FR-14 as amended 2026-10-07 (docs/brd_deviations.md D-02): one or two letters, two or three digits,
# so "Item GP-50" is FAA. The BRD text was Item [A-Z]-\d{3}.
_SPEC_FAA = re.compile(r"Item [A-Z]{1,2}-\d{2,3}")
_SPEC_PORT = re.compile(r"Section \d{6}")
_TOTAL_PREFIX = "Total Amount "
# Text the bid tab uses to say a value is absent. Read as null, and counted as a
# warning on the file. Any other text in a price cell is flagged.
# "Not provided": 2024-10691, unit prices of the non-responsive bidder.
NO_VALUE_MARKERS = frozenset({"not provided"})


def parse_amount(text: str | None, field: str, page_no: int) -> float | None:
    """'$1,595,000.00' -> 1595000.0; blank or a known no-value marker -> None; anything else is flagged."""
    value = (text or "").strip()
    if not value or value.lower() in NO_VALUE_MARKERS:
        return None
    m = _AMOUNT.fullmatch(value)
    if not m:
        raise LayoutFlag("amount_unrecognized", f"{field} {value!r}", page_no)
    return float(m.group(1).replace(",", "") + (m.group(2) or ""))


def split_spec_ref(cell: str | None) -> tuple[str, str | None]:
    """(description with spec reference, spec reference) for a description cell (FR-13, FR-14)."""
    lines = cell_lines(cell)
    spec = None
    if lines:
        m = _SPEC_LINE.fullmatch(lines[-1])
        if m:
            spec = m.group(1)
    return " ".join(lines), spec


def spec_ref_type(spec_ref_raw: str | None) -> str | None:
    """FR-14 (amended): FAA for 'Item X-999' or 'Item XX-99', PORT for 'Section 999999', otherwise UNK."""
    if spec_ref_raw is None:
        return None
    if _SPEC_FAA.fullmatch(spec_ref_raw):
        return "FAA"
    if _SPEC_PORT.fullmatch(spec_ref_raw):
        return "PORT"
    return "UNK"


def parse_detail_table(table: list[list[str | None]], page_no: int) -> DetailPage:
    if len(table) < 2:
        raise LayoutFlag("detail_unrecognized", "fewer than two table rows", page_no)
    row0 = table[0]
    n_bidders = (len(row0) - len(BASE_COLUMNS)) // 2
    if n_bidders < 1 or len(row0) != len(BASE_COLUMNS) + 2 * n_bidders:
        raise LayoutFlag("bidder_header_unrecognized", f"{len(row0)} header columns", page_no)
    bidders = []
    for j in range(n_bidders):
        name, merged = one_line(row0[4 + 2 * j]), one_line(row0[5 + 2 * j])
        if not name or merged:
            raise LayoutFlag("bidder_header_unrecognized", f"bidder column {j + 1}: {name!r} / {merged!r}", page_no)
        bidders.append(name)
    header = parse_header_block(row0[0], page_no)

    expected_columns = BASE_COLUMNS + PRICE_COLUMNS * n_bidders
    got_columns = [one_line(c) for c in table[1]]
    if got_columns != expected_columns:
        raise LayoutFlag("column_header_unrecognized", f"{got_columns!r}", page_no)

    rows: list[ItemLine | TotalLine] = []
    markers = 0
    for raw in table[2:]:
        cells = list(raw) + [None] * (len(expected_columns) - len(raw))
        item_no, label = one_line(cells[0]), one_line(cells[1])
        if not item_no and not any(one_line(c) for c in cells):
            continue
        if item_no:
            if not _ITEM_NO.fullmatch(item_no):
                raise LayoutFlag("item_number_unrecognized", f"{item_no!r}", page_no)
            markers += sum(one_line(c).lower() in NO_VALUE_MARKERS for c in cells[4:])
            description, spec = split_spec_ref(cells[1])
            if not description:
                raise LayoutFlag("row_unrecognized", f"item {item_no} has no description", page_no)
            prices = [
                (
                    parse_amount(cells[4 + 2 * j], "unit_price", page_no),
                    parse_amount(cells[5 + 2 * j], "total_price", page_no),
                )
                for j in range(n_bidders)
            ]
            rows.append(
                ItemLine(
                    item_no=item_no,
                    description=description,
                    spec_ref_raw=spec,
                    quantity=parse_amount(cells[2], "quantity", page_no),
                    unit=one_line(cells[3]),
                    prices=prices,
                    page_no=page_no,
                )
            )
        elif label.startswith(_TOTAL_PREFIX) and not any(one_line(c) for c in cells[2:5]):
            amounts = [parse_amount(cells[5 + 2 * j], "total", page_no) for j in range(n_bidders)]
            rows.append(TotalLine(label=label[len(_TOTAL_PREFIX) :], amounts=amounts, page_no=page_no))
        else:
            raise LayoutFlag("row_unrecognized", f"{[one_line(c) for c in cells]!r}", page_no)
    return DetailPage(page_no=page_no, header=header, bidders=bidders, rows=rows, no_value_cells=markers)
