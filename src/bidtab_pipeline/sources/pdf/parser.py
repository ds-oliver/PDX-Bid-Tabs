"""Parse one compiled bid tab PDF into items, control totals, and schedule structure.

Document structure (all 17 fixtures):

- Page 1 is the summary: bidder x schedule totals, Engineer's Estimate last.
- Detail pages follow, schedule by schedule. Each page shows up to three
  bidders; a schedule's pages repeat once per bidder group. A run of pages that
  ends with a "Total Amount ..." row is a segment: one schedule for one group.
- After a schedule total, further total rows on the same page are roll-ups
  (for example "Base Bid and Additive Alternate A", or "Bid Schedules A and B
  (Basis of Award)"). They are control totals, not schedules. A roll-up covers
  every schedule up to and including the one it closes.

Cross-page rules, each flagged when broken:

- Every detail page repeats the summary's EAN and solicitation number, and all
  detail pages show the same bid date. A summary date that differs from the
  detail date is a warning, not a flag (2024-10569: 2/9/2025 vs 2/4/2025).
- A segment keeps one bidder group; a schedule's groups list the same items.
- Every schedule covers every group, and the groups together are exactly the
  summary's bidders.
- Summary columns map onto detail totals: the one base column to the single
  "(Basis of Award)" total, alternate columns to alternate schedules in order.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

from bidtab_pipeline.sources.pdf.detail import parse_detail_table, spec_ref_type
from bidtab_pipeline.sources.pdf.model import (
    DetailItem,
    DetailPage,
    DetailTotal,
    HeaderBlock,
    ItemLine,
    LayoutFlag,
    ParsedBidTab,
    Schedule,
    SummaryTarget,
    SummaryTotal,
    TotalLine,
)
from bidtab_pipeline.sources.pdf.summary import classify_footnote, parse_summary_table, summary_footnote
from bidtab_pipeline.sources.pdf.tables import page_table
from bidtab_pipeline.sources.xlsx.parser import classify_bidder

_ALTERNATE = re.compile(r"\b(Alternate|Alt\.?)\b", re.IGNORECASE)
_BASIS_OF_AWARD = "(Basis of Award)"


def bidder_key(name: str) -> str:
    """Match key for bidder names: the PDF text layer has kerning gaps ('P aving')."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def schedule_kind(label: str) -> str:
    return "alternate" if _ALTERNATE.search(label) else "base"


@dataclass
class _Segment:
    bidders: list[str]
    items: list[ItemLine] = field(default_factory=list)
    label: str | None = None
    totals: list[TotalLine] = field(default_factory=list)  # schedule total, then roll-ups


def parse_bid_tab(path: str | Path) -> ParsedBidTab:
    path = Path(path)
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        producer = (pdf.metadata or {}).get("Producer")
        if page_count < 2:
            raise LayoutFlag("page_count", f"{page_count} page(s); expected a summary page and detail pages")
        summary_page = pdf.pages[0]
        header, labels, summary_totals = parse_summary_table(page_table(summary_page, 1), page_no=1)
        footnote = summary_footnote(summary_page.extract_text() or "")
        detail_pages = [
            parse_detail_table(page_table(page, number), number) for number, page in enumerate(pdf.pages[1:], start=2)
        ]
    return assemble(path.name, page_count, producer, header, labels, summary_totals, footnote, detail_pages)


def assemble(
    file_name: str,
    page_count: int,
    producer: str | None,
    header: HeaderBlock,
    labels: list[str],
    summary_totals: list[SummaryTotal],
    footnote: str | None,
    detail_pages: list[DetailPage],
) -> ParsedBidTab:
    warnings = _check_headers(header, detail_pages)
    no_value = sum(p.no_value_cells for p in detail_pages)
    if no_value:
        warnings.append(f"price_not_provided: {no_value} price cells read 'Not provided' and are null")
    segments = _segments(detail_pages)
    groups, schedules_segments = _schedules(segments)
    _check_bidders(groups, summary_totals)

    positions = {}
    for group in groups:
        for name in group:
            positions[name] = len(positions) + 1

    schedules: list[Schedule] = []
    items: list[DetailItem] = []
    detail_totals: list[DetailTotal] = []
    rollups: list[str] = []
    for order, (label, segs) in enumerate(schedules_segments, start=1):
        kind = schedule_kind(label)
        schedules.append(Schedule(label=label, kind=kind, order=order, item_count=len(segs[0].items)))
        for seg in segs:
            for line in seg.items:
                for j, bidder in enumerate(seg.bidders):
                    unit_price, total_price = line.prices[j]
                    items.append(
                        DetailItem(
                            schedule_label=label,
                            schedule_kind=kind,
                            schedule_order=order,
                            item_no=line.item_no,
                            description=line.description,
                            spec_ref_raw=line.spec_ref_raw,
                            spec_ref_type=spec_ref_type(line.spec_ref_raw),
                            quantity=line.quantity,
                            unit=line.unit,
                            bidder=bidder,
                            contractor_position=positions[bidder],
                            is_engineers_estimate=classify_bidder(bidder)[1],
                            unit_price=unit_price,
                            total_price=total_price,
                            page_no=line.page_no,
                        )
                    )
            for i, total in enumerate(seg.totals):
                is_rollup = i > 0
                if is_rollup and total.label not in rollups:
                    rollups.append(total.label)
                for j, bidder in enumerate(seg.bidders):
                    detail_totals.append(
                        DetailTotal(
                            label=total.label,
                            kind="rollup" if is_rollup else kind,
                            schedule_order=None if is_rollup else order,
                            covers=tuple(range(1, order + 1)) if is_rollup else (order,),
                            bidder=bidder,
                            contractor_position=positions[bidder],
                            is_engineers_estimate=classify_bidder(bidder)[1],
                            amount=total.amounts[j],
                            page_no=total.page_no,
                        )
                    )

    return ParsedBidTab(
        file_name=file_name,
        page_count=page_count,
        producer=producer,
        header=header,
        summary_labels=labels,
        summary_totals=summary_totals,
        footnote_text=footnote,
        is_corrected_footnote=classify_footnote(footnote),
        bidder_groups=groups,
        schedules=schedules,
        rollups=rollups,
        items=items,
        detail_totals=detail_totals,
        summary_targets=_summary_targets(labels, schedules, detail_totals),
        detail_header=detail_pages[0].header,
        warnings=warnings,
    )


def _check_headers(header: HeaderBlock, pages: list[DetailPage]) -> list[str]:
    detail_date = pages[0].header.bid_date_raw
    for page in pages:
        got = (page.header.ean, page.header.solicitation_no)
        want = (header.ean, header.solicitation_no)
        if got != want:
            raise LayoutFlag("header_block_mismatch", f"detail header {got} differs from summary {want}", page.page_no)
        if page.header.bid_date_raw != detail_date:
            raise LayoutFlag(
                "header_block_mismatch",
                f"detail date {page.header.bid_date_raw} differs from page {pages[0].page_no} ({detail_date})",
                page.page_no,
            )
    if detail_date != header.bid_date_raw:
        return [f"summary_date_differs: summary {header.bid_date_raw}, detail pages {detail_date}"]
    return []


def _segments(pages: list[DetailPage]) -> list[_Segment]:
    segments: list[_Segment] = []
    current: _Segment | None = None
    for page in pages:
        if current is None:
            current = _Segment(bidders=page.bidders)
        elif page.bidders != current.bidders:
            raise LayoutFlag(
                "bidder_group_changed",
                f"bidders {page.bidders} before the schedule total for {current.bidders}",
                page.page_no,
            )
        closed_on_this_page = False
        for row in page.rows:
            if isinstance(row, ItemLine):
                if closed_on_this_page:
                    raise LayoutFlag("items_after_total", f"item {row.item_no} follows a total row", page.page_no)
                current.items.append(row)
            elif current.label is None:
                if not current.items:
                    raise LayoutFlag("empty_schedule", f"total row {row.label!r} with no items", page.page_no)
                current.label = row.label
                current.totals.append(row)
                closed_on_this_page = True
            else:
                current.totals.append(row)  # roll-up total after the schedule total
        if current.label is not None:
            segments.append(current)
            current = None
    if current is not None:
        raise LayoutFlag("schedule_not_closed", "detail pages end before a total row", pages[-1].page_no)
    if not segments:
        raise LayoutFlag("no_schedules", "no detail schedules found")
    return segments


def _schedules(segments: list[_Segment]) -> tuple[list[list[str]], list[tuple[str, list[_Segment]]]]:
    """Group segments into schedules; return bidder groups in order and (label, segments) per schedule."""
    groups: list[list[str]] = []
    schedules: list[tuple[str, list[_Segment]]] = []
    for seg in segments:
        if seg.bidders not in groups:
            groups.append(seg.bidders)
        last = schedules[-1] if schedules else None
        if last and last[0] == seg.label and all(s.bidders != seg.bidders for s in last[1]):
            last[1].append(seg)
        else:
            schedules.append((seg.label, [seg]))

    for label, segs in schedules:
        if len(segs) != len(groups):
            raise LayoutFlag(
                "schedule_missing_bidder_group", f"{label!r} covers {len(segs)} of {len(groups)} bidder groups"
            )
        reference = [(i.item_no, i.description, i.quantity, i.unit) for i in segs[0].items]
        for seg in segs[1:]:
            if [(i.item_no, i.description, i.quantity, i.unit) for i in seg.items] != reference:
                raise LayoutFlag(
                    "schedule_items_differ",
                    f"{label!r}: items for {seg.bidders} differ from {segs[0].bidders}",
                    seg.items[0].page_no if seg.items else None,
                )
    flat = [name for group in groups for name in group]
    if len(flat) != len(set(flat)):
        raise LayoutFlag("bidder_groups_overlap", f"{groups}")
    return groups, schedules


def _check_bidders(groups: list[list[str]], summary_totals: list[SummaryTotal]) -> None:
    detail = sorted(bidder_key(n) for g in groups for n in g)
    summary = sorted({bidder_key(t.bidder_name_raw) for t in summary_totals})
    if detail != summary:
        raise LayoutFlag("bidder_set_mismatch", f"detail bidders {detail} vs summary bidders {summary}")


def _summary_targets(
    labels: list[str], schedules: list[Schedule], detail_totals: list[DetailTotal]
) -> list[SummaryTarget]:
    """Map each summary column to the detail total it reports and the schedules it covers."""
    base_columns = [i for i, label in enumerate(labels) if schedule_kind(label) == "base"]
    alt_columns = [i for i, label in enumerate(labels) if schedule_kind(label) == "alternate"]
    alternates = [s for s in schedules if s.kind == "alternate"]
    covers = {t.label: t.covers for t in detail_totals}
    award = [label for label in covers if _BASIS_OF_AWARD in label]
    if len(base_columns) != 1 or len(award) != 1:
        raise LayoutFlag(
            "summary_schedule_mapping",
            f"expected one base summary column and one '{_BASIS_OF_AWARD}' total; "
            f"got columns {labels} and award totals {award}",
        )
    if len(alt_columns) != len(alternates):
        raise LayoutFlag(
            "summary_schedule_mapping",
            f"{len(alt_columns)} alternate summary columns vs {len(alternates)} alternate schedules",
        )
    award_label = award[0]
    award_schedule = next((s for s in schedules if s.label == award_label), None)
    base_orders = (award_schedule.order,) if award_schedule else tuple(s.order for s in schedules if s.kind == "base")
    targets = [SummaryTarget(base_columns[0], labels[base_columns[0]], award_label, base_orders)]
    for column, schedule in zip(alt_columns, alternates, strict=True):
        targets.append(SummaryTarget(column, labels[column], schedule.label, (schedule.order,)))
    return sorted(targets, key=lambda t: t.column_index)
