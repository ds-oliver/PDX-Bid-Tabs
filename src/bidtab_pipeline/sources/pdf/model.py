"""Types for the compiled bid tab PDF parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


class LayoutFlag(Exception):
    """The file does not match the known compiled bid tab layout.

    Unknown layouts are flagged with a reason, never guessed (BRD Section 10).
    A flagged file contributes no Bronze rows; the manifest records the code.
    """

    def __init__(self, code: str, detail: str, page_no: int | None = None) -> None:
        self.code = code
        self.detail = detail
        self.page_no = page_no
        where = f" (page {page_no})" if page_no is not None else ""
        super().__init__(f"{code}{where}: {detail}")


@dataclass(frozen=True)
class HeaderBlock:
    location_raw: str
    project_name_raw: str
    ean: str
    solicitation_no: str
    bid_date_raw: str
    bid_date: date


@dataclass(frozen=True)
class SummaryTotal:
    bidder_name_raw: str
    column_index: int
    column_label: str
    amount: float | None
    is_starred: bool
    is_engineers_estimate: bool
    page_no: int


@dataclass(frozen=True)
class ItemLine:
    item_no: str
    description: str
    spec_ref_raw: str | None
    quantity: float | None
    unit: str
    prices: list[tuple[float | None, float | None]]  # (unit price, total price) per bidder column
    page_no: int


@dataclass(frozen=True)
class TotalLine:
    label: str  # text after "Total Amount "
    amounts: list[float | None]  # per bidder column
    page_no: int


@dataclass
class DetailPage:
    page_no: int
    header: HeaderBlock
    bidders: list[str]
    rows: list[ItemLine | TotalLine]
    no_value_cells: int = 0  # price cells holding a no-value marker such as "Not provided"

    @property
    def items(self) -> list[ItemLine]:
        return [r for r in self.rows if isinstance(r, ItemLine)]

    @property
    def totals(self) -> list[TotalLine]:
        return [r for r in self.rows if isinstance(r, TotalLine)]


@dataclass(frozen=True)
class Schedule:
    label: str
    kind: str  # base | alternate
    order: int  # 1-based, in document order
    item_count: int


@dataclass(frozen=True)
class DetailItem:
    schedule_label: str
    schedule_kind: str
    schedule_order: int
    item_no: str
    description: str
    spec_ref_raw: str | None
    spec_ref_type: str | None
    quantity: float | None
    unit: str
    bidder: str
    contractor_position: int
    is_engineers_estimate: bool
    unit_price: float | None
    total_price: float | None
    page_no: int


@dataclass(frozen=True)
class DetailTotal:
    label: str
    kind: str  # base | alternate | rollup
    schedule_order: int | None  # None for rollups
    covers: tuple[int, ...]  # schedule orders this total adds up
    bidder: str
    contractor_position: int
    is_engineers_estimate: bool
    amount: float | None
    page_no: int


@dataclass(frozen=True)
class SummaryTarget:
    """What a summary-page column totals: the detail total row and the schedules it covers."""

    column_index: int
    column_label: str
    detail_label: str
    schedule_orders: tuple[int, ...]


@dataclass
class ParsedBidTab:
    file_name: str
    page_count: int
    producer: str | None
    header: HeaderBlock
    summary_labels: list[str]
    summary_totals: list[SummaryTotal]
    footnote_text: str | None
    is_corrected_footnote: bool | None
    bidder_groups: list[list[str]]
    schedules: list[Schedule]
    rollups: list[str]
    items: list[DetailItem]
    detail_totals: list[DetailTotal]
    summary_targets: list[SummaryTarget] = field(default_factory=list)
    # The header block repeated on the detail pages. Bronze rows use it: it is the
    # page each row comes from. It can differ from the summary page's header.
    detail_header: HeaderBlock | None = None
    # Data inconsistencies that do not stop the parse, e.g. a summary date that
    # differs from the detail pages' date (2024-10569).
    warnings: list[str] = field(default_factory=list)
