"""Landing, manifest, Bronze rows, and reconciliation over all 17 fixtures (FR-01 to FR-03, FR-50, DR-01 to DR-03)."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest

from bidtab_pipeline.contracts import BRONZE_PDF_BID_ITEMS, BRONZE_PDF_CONTROL_TOTALS, REF_FILE_MANIFEST
from bidtab_pipeline.sources.pdf.bronze import ingest_landing

PDF_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "pdf"
NOW = datetime(2026, 10, 7, 12, 0, 0)

# Summary-total reconciliation exceptions and their explanations (FR-50). Every
# failing check must be listed here with a cause; currently none fail.
EXPLAINED_EXCEPTIONS: dict[tuple[str, str, str], str] = {}


def blank_pdf_bytes() -> bytes:
    """A valid one-page PDF with no text layer."""
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>",
    ]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj".encode() + body + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 4\n0000000000 65535 f \n" + b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n" + str(xref).encode() + b"\n%%EOF\n"
    return bytes(out)


@pytest.fixture(scope="module")
def landing(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("pdf_landing")
    for pdf in PDF_DIR.glob("*.pdf"):
        shutil.copy2(pdf, root / pdf.name)
    shutil.copy2(PDF_DIR / "2024-10564 Bid Tab.pdf", root / "zz copy of 2024-10564.pdf")  # same hash
    (root / "notes.txt").write_text("not a pdf\n")
    (root / "renamed.pdf").write_bytes(b"PK\x03\x04 a zip, not a pdf")
    (root / "scan.pdf").write_bytes(blank_pdf_bytes())
    (root / "~$lock.pdf").write_bytes(b"lock")
    (root / "archive").mkdir()
    shutil.copy2(PDF_DIR / "2024-10564 Bid Tab.pdf", root / "archive" / "old.pdf")
    return root


@pytest.fixture(scope="module")
def result(landing):
    known = {"0" * 64: datetime(2020, 1, 1)}
    return ingest_landing(str(landing), first_seen=known, now=NOW)


def status(result, name):
    (row,) = (m for m in result.manifest if m["file_name"] == name)
    return row


def test_all_17_fixtures_parse(result):
    parsed = [m for m in result.manifest if m["parse_status"] == "parsed"]
    assert len(parsed) == 17
    assert all(m["item_rows"] > 0 and m["control_total_rows"] > 0 for m in parsed)


def test_rejections_duplicates_and_ignored_files(result):
    assert status(result, "notes.txt")["status_reason"] == "not_pdf"
    assert status(result, "renamed.pdf")["status_reason"] == "not_pdf"
    scan = status(result, "scan.pdf")
    assert (scan["parse_status"], scan["status_reason"], scan["has_text_layer"]) == ("rejected", "no_text_layer", False)
    dup = status(result, "zz copy of 2024-10564.pdf")
    assert (dup["parse_status"], dup["status_reason"]) == ("duplicate", "same_hash")
    assert "2024-10564 Bid Tab.pdf" in dup["error_text"]
    names = {m["file_name"] for m in result.manifest}
    assert "~$lock.pdf" not in names and "old.pdf" not in names  # lock files and subfolders ignored
    assert len(result.manifest) == 17 + 4


def test_warnings_are_recorded_on_parsed_files(result):
    assert "summary_date_differs" in status(result, "2024-10569 Bid Tab.pdf")["error_text"]
    assert "price_not_provided" in status(result, "2024-10691 Bid Tab.pdf")["error_text"]


def test_first_seen_kept_for_known_hashes(landing):
    sha = next(m["file_sha256"] for m in ingest_landing(str(landing), now=NOW).manifest if m["file_name"] == "scan.pdf")
    rerun = ingest_landing(str(landing), first_seen={sha: datetime(2025, 5, 5)}, now=NOW)
    assert status(rerun, "scan.pdf")["first_seen_at"] == datetime(2025, 5, 5)
    assert status(rerun, "notes.txt")["first_seen_at"] == NOW


def test_rows_match_contracts(result):
    assert list(result.manifest[0]) == [c for c, _ in REF_FILE_MANIFEST]
    assert list(result.items[0]) == [c for c, _ in BRONZE_PDF_BID_ITEMS if c != "bronze_loaded_at"]
    assert list(result.control_totals[0]) == [c for c, _ in BRONZE_PDF_CONTROL_TOTALS if c != "bronze_loaded_at"]


def test_bid_types_classify_like_the_workbooks(result):
    def types(sol):
        return sorted({r["bid_type"] for r in result.items if r["solicitation_no"] == sol})

    assert types("2024-10564") == ["Alternate Bid Tab", "Base Bid Tab"]
    assert types("2023-10383") == [
        "Alternate Bid Tab 1",
        "Alternate Bid Tab 2",
        "Base Bid Tab - Bid Schedule A",
        "Base Bid Tab - Bid Schedule B",
    ]
    assert types("2024-10691") == ["Base Bid Tab"]


def test_corrected_and_non_responsive_stars(result):
    starred = [r for r in result.control_totals if r["is_starred"]]
    assert {r["is_corrected_total"] for r in starred if r["solicitation_no"] != "2024-10691"} == {True}
    (pullman,) = (r for r in starred if r["solicitation_no"] == "2024-10691")
    assert pullman["is_corrected_total"] is False
    assert pullman["footnote_text"].startswith("*Non-responsive")


def test_reconciliation_gate(result):
    """Phase 3 gate: >= 95% of bidder x schedule summary totals reconcile within $1.00; every exception explained."""
    summary = [c for c in result.checks if c.check == "summary"]
    passed = [c for c in summary if c.passed]
    assert len(passed) / len(summary) >= 0.95
    unexplained = [
        c for c in summary if not c.passed and (c.solicitation_no, c.total_label, c.bidder) not in EXPLAINED_EXCEPTIONS
    ]
    assert not unexplained
