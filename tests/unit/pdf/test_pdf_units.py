"""Unit tests for PDF parsing rules on synthetic tables: FR-10 to FR-15 and the unknown-layout flags."""

from __future__ import annotations

import pytest

from bidtab_pipeline.sources.pdf.detail import parse_amount, parse_detail_table, spec_ref_type, split_spec_ref
from bidtab_pipeline.sources.pdf.header import parse_header_block
from bidtab_pipeline.sources.pdf.model import LayoutFlag
from bidtab_pipeline.sources.pdf.summary import classify_footnote, parse_summary_table

HEADER_TEXT = "PORTLAND INTERNATIONAL AIRPORT\nTAXIWAY Z\nREHAB\nEAN 2099D001\nSolicitation No. 2099-00001\n1/2/2025"
COLS = ["Item\nNo.", "Item Description", "Estimated\nQuantity", "Units", "Unit Price", "Total Price"]


def detail_table(rows, bidders=("Acme Co", "Engineer's Estimate")):
    row0 = [HEADER_TEXT, None, None, None]
    for b in bidders:
        row0 += [b, None]
    return [row0, COLS + ["Unit Price", "Total Price"] * (len(bidders) - 1), *rows]


# --- FR-10 header ------------------------------------------------------------------


def test_header_block_fields():
    h = parse_header_block(HEADER_TEXT)
    assert (h.location_raw, h.project_name_raw) == ("PORTLAND INTERNATIONAL AIRPORT", "TAXIWAY Z REHAB")
    assert (h.ean, h.solicitation_no, h.bid_date_raw, h.bid_date.isoformat()) == (
        "2099D001",
        "2099-00001",
        "1/2/2025",
        "2025-01-02",
    )


@pytest.mark.parametrize(
    "text",
    [
        "AIRPORT\nPROJECT\nSolicitation No. 2099-1\n1/2/2025",  # no EAN
        "AIRPORT\nPROJECT\nEAN 2099D001\n1/2/2025",  # no solicitation
        "AIRPORT\nPROJECT\nEAN 2099D001\nSolicitation No. 2099-1",  # no date
        "EAN 2099D001\nSolicitation No. 2099-1\n1/2/2025",  # no location or project
    ],
)
def test_header_block_incomplete_is_flagged(text):
    with pytest.raises(LayoutFlag) as info:
        parse_header_block(text)
    assert info.value.code == "header_block_unrecognized"


# --- FR-11 summary ------------------------------------------------------------------


def test_summary_table_and_stars():
    table = [
        [HEADER_TEXT, "", ""],
        ["Bidder", "Total Base Bid Price", "Total Additive\nAlternate A"],
        ["Acme Co", "$10.00*", "$2.50"],
        ["Engineer's Estimate", "$12.00", "$3.00"],
    ]
    header, labels, totals = parse_summary_table(table, page_no=1)
    assert header.ean == "2099D001"
    assert labels == ["Total Base Bid Price", "Total Additive Alternate A"]
    assert [(t.bidder_name_raw, t.column_index, t.amount, t.is_starred) for t in totals] == [
        ("Acme Co", 0, 10.0, True),
        ("Acme Co", 1, 2.5, False),
        ("Engineer's Estimate", 0, 12.0, False),
        ("Engineer's Estimate", 1, 3.0, False),
    ]


def test_summary_without_bidder_header_is_flagged():
    with pytest.raises(LayoutFlag) as info:
        parse_summary_table([[HEADER_TEXT, ""], ["Contractor", "Total"], ["Acme", "$1.00"]], page_no=1)
    assert info.value.code == "summary_unrecognized"


@pytest.mark.parametrize(
    ("text", "corrected"),
    [
        ("*Corrected Bid Total", True),
        ("*Non-responsive to the bid submission requirements of this solicitation", False),
        ("*Something new", None),  # unknown meaning: recorded, not guessed
    ],
)
def test_footnote_classification(text, corrected):
    assert classify_footnote(text) is corrected


# --- FR-12 to FR-14 detail ------------------------------------------------------------


def test_detail_rows_wrap_merge_and_spec_ref():
    page = parse_detail_table(
        detail_table(
            [
                [
                    "0001",
                    "Contaminated Material Excavation and\nDisposal\n(Section 026100)",
                    "1,500.0",
                    "Ton",
                    "$50.00",
                    "$75,000.00",
                    "$75.00",
                    "$112,500.00",
                ],
                ["", "Total Amount Base Bid", "", "", "", "$75,000.00", "", "$112,500.00"],
            ]
        ),
        page_no=4,
    )
    assert page.bidders == ["Acme Co", "Engineer's Estimate"]
    (item,) = page.items
    assert item.description == "Contaminated Material Excavation and Disposal (Section 026100)"
    assert (item.spec_ref_raw, item.quantity, item.unit) == ("Section 026100", 1500.0, "Ton")
    assert item.prices == [(50.0, 75000.0), (75.0, 112500.0)]
    (total,) = page.totals
    assert (total.label, total.amounts) == ("Base Bid", [75000.0, 112500.0])


@pytest.mark.parametrize(
    ("description", "raw", "kind"),
    [
        ("Sweeper\n(Section 012200)", "Section 012200", "PORT"),
        ("PCC Removal\n(Item P-101)", "Item P-101", "FAA"),
        ("Construction Survey\n(Item GP-50)", "Item GP-50", "FAA"),  # FR-14 amended (D-02)
        ("Paving\n(Item P-1001)", "Item P-1001", "UNK"),  # four digits: outside the FAA pattern
        ("Fence\n(Item ABC-10)", "Item ABC-10", "UNK"),  # three letters
        ("Survey\n(Section 01220)", "Section 01220", "UNK"),  # five digits
        ("Mobilization, Cleanup, and Demobilization", None, None),
    ],
)
def test_spec_ref_capture_and_type(description, raw, kind):
    _, got_raw = split_spec_ref(description)
    assert got_raw == raw
    assert spec_ref_type(got_raw) == kind


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("$1,595,000.00", 1595000.0),
        ("$0.00", 0.0),
        ("1,740.0", 1740.0),
        ("", None),
        (None, None),
        ("Not provided", None),  # explicit no-value marker (2024-10691)
    ],
)
def test_amounts(text, value):
    assert parse_amount(text, field="x", page_no=1) == value


@pytest.mark.parametrize("text", ["TBD", "$1,0O0.00", "N/A"])
def test_unparseable_amount_is_flagged(text):
    with pytest.raises(LayoutFlag) as info:
        parse_amount(text, field="unit_price", page_no=3)
    assert info.value.code == "amount_unrecognized"
    assert info.value.page_no == 3


# --- unknown layouts are flagged, never guessed (BRD Section 10) ----------------------


def test_unrecognized_column_header_is_flagged():
    table = detail_table([])
    table[1] = ["Item", "Description", "Qty", "Unit", "Price", "Extended"] + ["Unit Price", "Total Price"]
    with pytest.raises(LayoutFlag) as info:
        parse_detail_table(table, page_no=2)
    assert info.value.code == "column_header_unrecognized"


def test_unrecognized_item_number_is_flagged():
    with pytest.raises(LayoutFlag) as info:
        parse_detail_table(detail_table([["1-A", "Thing", "1.0", "LS", "$1.00", "$1.00", "$1.00", "$1.00"]]), page_no=2)
    assert info.value.code == "item_number_unrecognized"


def test_unrecognized_row_is_flagged():
    with pytest.raises(LayoutFlag) as info:
        parse_detail_table(detail_table([["", "Subtotal Paving", "", "", "", "$1.00", "", "$1.00"]]), page_no=2)
    assert info.value.code == "row_unrecognized"


def test_missing_bidder_name_is_flagged():
    table = detail_table([])
    table[0][4] = ""
    with pytest.raises(LayoutFlag) as info:
        parse_detail_table(table, page_no=2)
    assert info.value.code == "bidder_header_unrecognized"
