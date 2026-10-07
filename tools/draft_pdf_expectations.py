#!/usr/bin/env python3
"""Draft expected values for the PDF fixtures, independently of the parser.

Writes tests/fixtures/pdf_expected/<solicitation>.json. Each draft is reviewed
before it is committed; hand-checked files are marked "hand_checked": true after
comparison with the rendered pages.

Deliberately uses a different method from src/bidtab_pipeline/sources/pdf/:
page text lines and regular expressions, not ruled-table extraction. Agreement
between the two is evidence; a shared method would only repeat its own errors.

Usage (from the repo root):
    python tools/draft_pdf_expectations.py [SOLICITATION ...]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pdfplumber

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "pdf"
OUT = REPO / "tests" / "fixtures" / "pdf_expected"

AMOUNT = re.compile(r"\$[\d,]+\.\d{2}\*?")
ITEM_LINE = re.compile(r"^(\d{4})\s")


def summary(page) -> dict:
    lines = [ln.strip() for ln in page.extract_text().splitlines() if ln.strip()]
    ean = next(re.match(r"EAN (\S+)$", ln).group(1) for ln in lines if re.match(r"EAN \S+$", ln))
    sol = next(re.match(r"Solicitation No\. (\S+)$", ln).group(1) for ln in lines if ln.startswith("Solicitation No."))
    date = next(ln for ln in lines if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", ln))
    bidders, totals, starred, footnotes = [], [], [], []
    for ln in lines:
        amounts = AMOUNT.findall(ln)
        if amounts and not ln.startswith("$"):
            name = ln[: ln.index("$")].strip()
            bidders.append(name)
            totals.append([float(a.rstrip("*").replace("$", "").replace(",", "")) for a in amounts])
            starred.extend([name, i] for i, a in enumerate(amounts) if a.endswith("*"))
        elif ln.startswith("*"):
            footnotes.append(ln)
    return {
        "ean": ean,
        "solicitation_no": sol,
        "bid_date_raw": date,
        "summary_bidders": bidders,
        "summary_totals": totals,
        "starred": starred,
        "footnotes": footnotes,
    }


def detail_segments(pdf) -> list[dict]:
    """Pages between total rows form a segment: one schedule for one bidder group."""
    segments, items, pages = [], [], []
    for number, page in enumerate(pdf.pages[1:], start=2):
        pages.append(number)
        for ln in (s.strip() for s in page.extract_text().splitlines()):
            m = ITEM_LINE.match(ln)
            if m:
                items.append(m.group(1))
            elif ln.startswith("Total Amount") and items is not None:
                if pages:
                    segments.append({"pages": pages, "items": items})
                    items, pages = [], []
    return segments


def draft(pdf_path: Path) -> dict:
    with pdfplumber.open(pdf_path) as pdf:
        out = {"file": pdf_path.name, "pages": len(pdf.pages), "hand_checked": False, **summary(pdf.pages[0])}
        segs = detail_segments(pdf)
    out["segments"] = [{"pages": s["pages"], "item_count": len(s["items"])} for s in segs]
    return out


def main() -> int:
    wanted = set(sys.argv[1:])
    OUT.mkdir(parents=True, exist_ok=True)
    for path in sorted(FIXTURES.glob("*.pdf")):
        sol = path.name.split(" ")[0]
        if wanted and sol not in wanted:
            continue
        data = draft(path)
        (OUT / f"{sol}.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(sol, data["pages"], len(data["summary_bidders"]), [s["item_count"] for s in data["segments"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
