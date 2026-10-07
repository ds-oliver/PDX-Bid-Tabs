"""Summary page (FR-11): bidder x schedule totals, with the starred-total footnote.

A `*` after an amount points to a footnote below the table. The footnote's
meaning varies: "*Corrected Bid Total" in most files, but 2024-10691 uses it
for "*Non-responsive to the bid submission requirements of this solicitation".
The footnote text is kept; `is_corrected_total` is set only when it says
corrected, and left unknown for wording the parser has not seen.
"""

from __future__ import annotations

import re

from bidtab_pipeline.sources.pdf.header import parse_header_block
from bidtab_pipeline.sources.pdf.model import HeaderBlock, LayoutFlag, SummaryTotal
from bidtab_pipeline.sources.pdf.tables import one_line
from bidtab_pipeline.sources.xlsx.parser import classify_bidder

_SUMMARY_AMOUNT = re.compile(r"\$([\d,]+\.\d{2})(\*?)")


def parse_summary_table(
    table: list[list[str | None]], page_no: int
) -> tuple[HeaderBlock, list[str], list[SummaryTotal]]:
    if len(table) < 3 or one_line(table[1][0]) != "Bidder":
        raise LayoutFlag("summary_unrecognized", "expected a 'Bidder' header row under the header block", page_no)
    header = parse_header_block(table[0][0], page_no)
    labels = [one_line(c) for c in table[1][1:]]
    if not labels or not all(labels):
        raise LayoutFlag("summary_unrecognized", f"blank schedule column label in {labels!r}", page_no)

    totals: list[SummaryTotal] = []
    for row in table[2:]:
        cells = [one_line(c) for c in row]
        if not any(cells):
            continue
        name = cells[0]
        if not name or len(cells) != len(labels) + 1:
            raise LayoutFlag("summary_unrecognized", f"unexpected summary row {cells!r}", page_no)
        _, is_ee = classify_bidder(name)
        for index, (label, text) in enumerate(zip(labels, cells[1:], strict=True)):
            amount, starred = None, False
            if text:
                m = _SUMMARY_AMOUNT.fullmatch(text)
                if not m:
                    raise LayoutFlag("amount_unrecognized", f"summary amount {text!r} for {name!r}", page_no)
                amount, starred = float(m.group(1).replace(",", "")), m.group(2) == "*"
            totals.append(SummaryTotal(name, index, label, amount, starred, is_ee, page_no))
    if not totals:
        raise LayoutFlag("summary_unrecognized", "no bidder rows", page_no)
    return header, labels, totals


def summary_footnote(page_text: str) -> str | None:
    """Footnote lines below the summary table start with '*' and carry no amount."""
    notes = [ln.strip() for ln in page_text.splitlines() if ln.strip().startswith("*") and "$" not in ln]
    return " ".join(notes) or None


def classify_footnote(text: str | None) -> bool | None:
    """True for a corrected-total footnote, False for a known other meaning, None if unknown."""
    if not text:
        return None
    lowered = text.lower()
    if "corrected" in lowered:
        return True
    if "non-responsive" in lowered or "nonresponsive" in lowered:
        return False
    return None
