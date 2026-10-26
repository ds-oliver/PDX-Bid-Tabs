"""Control-total reconciliation for the PDF source (FR-50).

Two checks per bidder:

- summary: each summary-page total (bidder x summary schedule) against the sum
  of item total prices over the schedules that column covers. This is FR-50 and
  the Phase 3 gate metric.
- detail: each detail total row (schedule totals and roll-ups) against the sum
  of item total prices over the schedules it covers.

A check passes when the difference is at most $1.00. Mismatches are reported,
never fixed, and do not stop the run. Null item totals count as zero and are
noted on the check.
"""

from __future__ import annotations

from dataclasses import dataclass

from bidtab_pipeline.sources.pdf.model import ParsedBidTab
from bidtab_pipeline.sources.pdf.parser import bidder_key

TOLERANCE = 1.00


@dataclass(frozen=True)
class Check:
    source_file: str
    solicitation_no: str
    check: str  # summary | detail
    total_label: str
    bidder: str
    is_engineers_estimate: bool
    reported_total: float | None
    item_sum: float
    difference: float | None
    passed: bool
    is_starred: bool
    note: str


def _item_sums(parsed: ParsedBidTab, orders: tuple[int, ...], bidder: str) -> tuple[float, int]:
    k = bidder_key(bidder)
    rows = [i for i in parsed.items if i.schedule_order in orders and bidder_key(i.bidder) == k]
    nulls = sum(1 for i in rows if i.total_price is None)
    return round(sum(i.total_price or 0.0 for i in rows), 2), nulls


def _check(parsed, kind, label, bidder, is_ee, reported, orders, starred) -> Check:
    total, nulls = _item_sums(parsed, orders, bidder)
    diff = None if reported is None else round(total - reported, 2)
    notes = []
    if reported is None:
        notes.append("no reported total")
    if nulls:
        notes.append(f"{nulls} null item totals counted as 0")
    if starred:
        notes.append("starred total: " + (parsed.footnote_text or "no footnote"))
    return Check(
        source_file=parsed.file_name,
        solicitation_no=parsed.header.solicitation_no,
        check=kind,
        total_label=label,
        bidder=bidder,
        is_engineers_estimate=is_ee,
        reported_total=reported,
        item_sum=total,
        difference=diff,
        passed=diff is not None and abs(diff) <= TOLERANCE,
        is_starred=starred,
        note="; ".join(notes),
    )


def reconcile(parsed: ParsedBidTab) -> list[Check]:
    checks: list[Check] = []
    targets = {t.column_index: t for t in parsed.summary_targets}
    for total in parsed.summary_totals:
        target = targets[total.column_index]
        checks.append(
            _check(
                parsed,
                "summary",
                total.column_label,
                total.bidder_name_raw,
                total.is_engineers_estimate,
                total.amount,
                target.schedule_orders,
                total.is_starred,
            )
        )
    for total in parsed.detail_totals:
        checks.append(
            _check(
                parsed,
                "detail",
                total.label,
                total.bidder,
                total.is_engineers_estimate,
                total.amount,
                total.covers,
                False,
            )
        )
    return checks
