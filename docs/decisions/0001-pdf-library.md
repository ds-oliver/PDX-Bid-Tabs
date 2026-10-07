# 0001: PDF library for compiled bid tabs

**Status:** Accepted 2026-10-07. Library: `pdfplumber==0.11.4` (MIT), on `pdfminer.six`.

## Context

The 17 compiled bid tab PDFs are Excel sheets printed with cell borders (16 by
Bluebeam, 1 by Adobe PDF Library), 3 to 31 pages, all with a text layer. Detail
pages hold up to three bidders as Unit Price / Total Price column pairs;
descriptions wrap inside their cell with the spec reference on its own line.
NFR-02 requires open-source Python libraries on existing compute, no paid
per-page service. The library must run on Databricks Serverless (Python 3.10)
from PyPI or an uploaded wheel.

## Decision

Use pdfplumber's line-based table finder
(`{"vertical_strategy": "lines", "horizontal_strategy": "lines"}`). Because the
sheets are fully ruled, it returns one table per page with each cell's wrapped
text kept together and amounts in their own column. Column assignment comes
from the ruling, not from estimating x positions, and the same call works on
portrait, landscape, and rotated pages.

On the 17 fixtures: every page yields exactly one table; all 17 files parse;
149 of 149 summary totals and 177 of 177 detail totals reconcile with the item
sums within $1.00.

## Alternatives considered

| Library | Why not |
|---|---|
| Word coordinates only (pdfplumber `extract_words`, or pdfminer) | Workable but needs our own column and row-band logic and wrap merging; the ruled-table finder does this from the borders. Kept as the fallback if a future layout has no ruling. |
| Camelot (lattice mode) | Also finds ruled tables, but needs Ghostscript or OpenCV system packages, which Serverless compute may not allow. |
| tabula-py | Needs a Java runtime in the Python environment; another dependency to clear with Port IT. |
| PyMuPDF (fitz) | AGPL-3.0, or a commercial license: not suitable to ship in Port code without legal review. |
| pypdf | Text extraction without layout or table structure. |
| Paid OCR or table services (Textract, Azure Document Intelligence) | Excluded by NFR-02 for the MVP; only relevant to the OCR fallback (FR-18, future). |

## Consequences

- `pdfplumber` and its dependencies (`pdfminer.six`, `pypdfium2`, `Pillow`,
  `charset-normalizer`, `cryptography`) must be installed in the job
  environment. They are not in the production `requirements.txt`; PyPI access on
  the Port workspace needs confirmation (`docs/databricks_test_runbook.md`).
- Text from the PDF can carry kerning gaps (summary page "Acme Concrete P aving,
  Inc." vs detail page "Acme Concrete Paving, Inc."). Bidder names are matched on
  a key that ignores spaces and punctuation; raw text is kept.
- A layout without ruling lines, or with more than one table on a page, is
  flagged (`table_count`), not guessed.
