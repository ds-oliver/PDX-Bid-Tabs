"""Parser tests against the 17 compiled bid tab PDFs (NFR-08).

Expected values live in tests/fixtures/pdf_expected/<solicitation>.json. They
were drafted by tools/draft_pdf_expectations.py, which reads page text lines,
not ruled tables, so it shares no extraction logic with the parser. Files
marked "hand_checked" were also compared with the rendered pages; their extra
fields (bidder groups, schedules, spot rows, detail totals) come from that
check.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

import pytest

from bidtab_pipeline.sources.pdf.parser import parse_bid_tab

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
PDF_DIR = FIXTURES / "pdf"
EXPECTED_DIR = FIXTURES / "pdf_expected"
SOLICITATIONS = sorted(p.stem for p in EXPECTED_DIR.glob("*.json"))
HAND_CHECKED = [s for s in SOLICITATIONS if json.loads((EXPECTED_DIR / f"{s}.json").read_text())["hand_checked"]]


def key(name: str) -> str:
    """Bidder match key: PDF text has kerning gaps ("P aving"), so ignore spaces and punctuation."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


@cache
def expected(sol: str) -> dict:
    return json.loads((EXPECTED_DIR / f"{sol}.json").read_text(encoding="utf-8"))


@cache
def parsed(sol: str):
    return parse_bid_tab(PDF_DIR / expected(sol)["file"])


def test_all_17_fixtures_have_expectations():
    assert len(SOLICITATIONS) == 17
    assert len(HAND_CHECKED) >= 3
    assert "2018-7876" in HAND_CHECKED
    assert any(expected(s)["pages"] == 31 for s in HAND_CHECKED)


@pytest.mark.parametrize("sol", SOLICITATIONS)
def test_header(sol):
    exp, got = expected(sol), parsed(sol)
    assert got.page_count == exp["pages"]
    assert got.header.ean == exp["ean"]
    assert got.header.solicitation_no == exp["solicitation_no"]
    assert got.header.bid_date_raw == exp["bid_date_raw"]


@pytest.mark.parametrize("sol", SOLICITATIONS)
def test_summary_bidders_totals_and_stars(sol):
    exp, got = expected(sol), parsed(sol)
    got_rows = {}
    for t in got.summary_totals:
        got_rows.setdefault(key(t.bidder_name_raw), []).append(t)
    assert list(got_rows) == [key(b) for b in exp["summary_bidders"]]
    for bidder, amounts in zip(exp["summary_bidders"], exp["summary_totals"], strict=True):
        assert [t.amount for t in sorted(got_rows[key(bidder)], key=lambda t: t.column_index)] == amounts
    got_starred = sorted([key(t.bidder_name_raw), t.column_index] for t in got.summary_totals if t.is_starred)
    assert got_starred == sorted([key(b), i] for b, i in exp["starred"])
    assert (got.footnote_text or None) == (exp["footnotes"][0] if exp["footnotes"] else None)


@pytest.mark.parametrize("sol", SOLICITATIONS)
def test_items_per_page_segment(sol):
    """Each run of pages closed by a total row holds one schedule for one bidder group."""
    exp, got = expected(sol), parsed(sol)
    for segment in exp["segments"]:
        pages = set(segment["pages"])
        item_nos = {(i.schedule_order, i.item_no) for i in got.items if i.page_no in pages}
        assert len(item_nos) == segment["item_count"], f"pages {segment['pages']}"


@pytest.mark.parametrize("sol", SOLICITATIONS)
def test_every_bidder_priced_on_every_item(sol):
    got = parsed(sol)
    n_bidders = len({key(t.bidder_name_raw) for t in got.summary_totals})
    assert len(got.items) == sum(s.item_count for s in got.schedules) * n_bidders
    detail_bidders = {key(i.bidder) for i in got.items}
    assert detail_bidders == {key(t.bidder_name_raw) for t in got.summary_totals}


@pytest.mark.parametrize("sol", SOLICITATIONS)
def test_engineers_estimate_kept_and_flagged(sol):
    got = parsed(sol)
    ee = {i.bidder for i in got.items if i.is_engineers_estimate}
    assert ee == {"Engineer's Estimate"}
    assert all(t.is_engineers_estimate == (t.bidder_name_raw == "Engineer's Estimate") for t in got.summary_totals)


# --- hand-checked fixtures ---------------------------------------------------------


@pytest.mark.parametrize("sol", HAND_CHECKED)
def test_hand_checked_header_names(sol):
    exp, got = expected(sol), parsed(sol)
    assert got.header.location_raw == exp["location_raw"]
    assert got.header.project_name_raw == exp["project_name_raw"]


@pytest.mark.parametrize("sol", HAND_CHECKED)
def test_hand_checked_bidder_groups(sol):
    assert parsed(sol).bidder_groups == expected(sol)["bidder_groups"]


@pytest.mark.parametrize("sol", HAND_CHECKED)
def test_hand_checked_schedules(sol):
    got = parsed(sol)
    assert [{"label": s.label, "kind": s.kind, "item_count": s.item_count} for s in got.schedules] == expected(sol)[
        "schedules"
    ]
    assert got.rollups == expected(sol)["rollups"]


@pytest.mark.parametrize("sol", HAND_CHECKED)
def test_hand_checked_rows(sol):
    exp, got = expected(sol), parsed(sol)
    by_key = {(i.schedule_label, i.item_no, i.bidder): i for i in got.items}
    rows = exp.get("all_rows") or exp["spot_rows"]
    for row in rows:
        item = by_key[(row["schedule"], row["item_no"], row["bidder"])]
        assert item.description == row["description"]
        assert item.spec_ref_raw == row["spec_ref_raw"]
        assert item.spec_ref_type == row["spec_ref_type"]
        assert item.quantity == row["quantity"]
        assert item.unit == row["unit"]
        assert item.unit_price == row["unit_price"]
        assert item.total_price == row["total_price"]
        assert item.page_no == row["page_no"]
        if "contractor_position" in row:
            assert item.contractor_position == row["contractor_position"]
    if "all_rows" in exp:
        assert len(got.items) == len(rows)


@pytest.mark.parametrize("sol", HAND_CHECKED)
def test_hand_checked_detail_totals(sol):
    got = parsed(sol)
    by_key = {(t.label, t.bidder, t.page_no): t.amount for t in got.detail_totals}
    for t in expected(sol)["detail_totals"]:
        assert by_key[(t["label"], t["bidder"], t["page_no"])] == t["amount"]
