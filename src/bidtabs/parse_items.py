from __future__ import annotations

import re
from decimal import Decimal
from typing import Dict, Iterable, List

from openpyxl.worksheet.worksheet import Worksheet

from .normalize import clean_whitespace, normalize_unit_code, parse_decimal
from .parse_table import BidderBlock

ITEM_CODE_PATTERNS = [
    re.compile(r"\((?:Item)\s+([A-Za-z]-?\d+(?:\.\d+)?)\)", re.IGNORECASE),
    re.compile(r"Item\s+([A-Za-z]-?\d+(?:\.\d+)?)", re.IGNORECASE),
]
SECTION_CODE_PATTERN = re.compile(r"\((?:Section)\s+([0-9]{4,6})\)", re.IGNORECASE)
TOTALS_PATTERN = re.compile(r"(total amount|basis of award)", re.IGNORECASE)


def extract_item_tokens(description: str) -> Dict[str, str]:
    desc = clean_whitespace(description)
    item_code_raw = ""
    section_code_raw = ""

    for p in ITEM_CODE_PATTERNS:
        m = p.search(desc)
        if m:
            item_code_raw = clean_whitespace(m.group(1))
            break

    m2 = SECTION_CODE_PATTERN.search(desc)
    if m2:
        section_code_raw = clean_whitespace(m2.group(1))

    item_code_norm = item_code_raw.upper().replace(" ", "") if item_code_raw else ""
    section_code_norm = re.sub(r"\D", "", section_code_raw) if section_code_raw else ""

    return {
        "item_code_raw": item_code_raw,
        "item_code_norm": item_code_norm,
        "section_code_raw": section_code_raw,
        "section_code_norm": section_code_norm,
    }


def _decimal_to_float(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _extract_line_no(ws: Worksheet, row: int, col: int) -> str:
    cell = ws.cell(row=row, column=col)
    raw = cell.value
    if raw is None:
        return ""
    if isinstance(raw, str):
        return clean_whitespace(raw)
    if isinstance(raw, (int, float)):
        num_format = clean_whitespace(cell.number_format)
        if num_format and set(num_format) <= {"0"}:
            width = len(num_format)
            try:
                return str(int(raw)).zfill(width)
            except Exception:
                pass
        if int(raw) == raw:
            return str(int(raw))
        return clean_whitespace(raw)
    return clean_whitespace(raw)


def iter_item_rows(
    ws: Worksheet,
    table_header_row: int,
    col_map: Dict[str, int],
    bidder_blocks: List[BidderBlock],
    termination_blank_streak: int = 10,
) -> Iterable[dict]:
    blank_streak = 0
    row = table_header_row + 1

    while row <= ws.max_row:
        line_no_raw = ws.cell(row=row, column=col_map["line_no_col"]).value
        desc_raw = ws.cell(row=row, column=col_map["desc_col"]).value
        qty_raw = ws.cell(row=row, column=col_map["qty_col"]).value
        unit_raw = ws.cell(row=row, column=col_map["unit_col"]).value

        line_no = _extract_line_no(ws, row, col_map["line_no_col"])
        desc = clean_whitespace(desc_raw)

        if not line_no and not desc:
            blank_streak += 1
            if blank_streak >= termination_blank_streak:
                break
            row += 1
            continue

        blank_streak = 0
        is_totals = bool(TOTALS_PATTERN.search(desc))
        tokens = extract_item_tokens(desc)
        qty = parse_decimal(qty_raw)
        unit_norm = normalize_unit_code(unit_raw) if unit_raw is not None else ""

        if line_no or is_totals:
            for block in bidder_blocks:
                unit_price = parse_decimal(ws.cell(row=row, column=block.unit_price_col).value)
                total_price = parse_decimal(ws.cell(row=row, column=block.total_price_col).value)
                schedule_total = total_price if is_totals else None
                record = {
                    "source_row_index": row,
                    "line_no": "" if is_totals else line_no,
                    "item_description_raw": desc,
                    "item_description_clean": desc,
                    "quantity": None if is_totals else _decimal_to_float(qty),
                    "unit_code_raw": "" if is_totals else clean_whitespace(unit_raw),
                    "unit_code_norm": "" if is_totals else unit_norm,
                    "unit_price": None if is_totals else _decimal_to_float(unit_price),
                    "total_price": None if is_totals else _decimal_to_float(total_price),
                    "schedule_total": _decimal_to_float(schedule_total),
                    "is_totals_row": is_totals,
                    "totals_row_label": desc if is_totals else "",
                    "bidder_name_raw": block.bidder_name_raw,
                    **tokens,
                }
                yield record
        row += 1
