# Deviations from the BRD

Approved departures from `docs/BidTab_PDF_Ingestion_BRD.md` (local only; Draft v0.2,
2026-10-09). Each entry names the BRD text, the change, who approved it, and where it
lives. BRD v0.2 Appendix A carries D-01 to D-04 in short form, and v0.2 already states
FR-14 (D-02), FR-21 (D-03) and DR-01 (D-04) as amended; this file keeps the detail.
BRD references below use v0.2 IDs and section numbers.

| # | BRD reference | BRD says | Implemented | Approved | Where |
|---|---|---|---|---|---|
| D-01 | Section 4 (compiled bid tab PDFs); Section 8 Track A exit criteria | 16 sample PDFs | 17 fixtures. 16 are byte-identical to the BRD samples; 2025-12566 is an additional compiled bid tab. Exit criteria apply to 17. 2018-7876 (EAN 2017D013) stays in parser tests and is excluded from parity, having no xlsx counterpart. | Hogan, 2026-10-07 (handoff Section 1, decision 3; hash check) | `tests/fixtures/pdf/`, `docs/pdf_source_notes.md` |
| D-02 | FR-14 | `spec_ref_type` is FAA when the reference matches `Item [A-Z]-\d{3}` | FAA pattern is `Item [A-Z]{1,2}-\d{2,3}`, so two-letter FAA items such as `(Item GP-50)` classify as FAA instead of UNK. PORT stays `Section \d{6}`; anything else is UNK. | Hogan, 2026-10-07 | `src/bidtab_pipeline/sources/pdf/detail.py` (`spec_ref_type`), `tests/unit/pdf/test_pdf_units.py` |
| D-03 | FR-12 (item number); FR-21 (schedule label); DR-02 (compatible with `bronze_raw_rows`) | Item number as printed; keep the schedule label | When a file has more than one base schedule, every base schedule gets `bid_type = 'Base Bid Tab'` and `item_no` takes the printed schedule letter as a prefix (`Bid Schedule A` item `0001` becomes `A-0001`). Files with one base schedule keep printed item numbers. `bid_type` stays within the six values `01` can produce. `source_sheet` and `schedule_label` keep the printed schedule label. One warning per affected file (`base_schedules_prefixed`, in the manifest). Affects 2023-10383 among the fixtures. Reasons: the Power BI model derives a bid type sort order from `bid_type` values (v0.2 Section 3, Environment and serving; Final Report Appendix D), so a new value such as `Base Bid Tab - Bid Schedule A` would fall outside it; item numbers restart per schedule, so without a prefix 60 `natural_key` values would collide; 2021D007 is the production precedent for prefixed item numbers (`1-001`). | Hogan, 2026-10-07 | `src/bidtab_pipeline/sources/pdf/bronze.py` (`bid_type`, `base_item_prefixes`), `tests/unit/pdf/test_pdf_ingest.py`, `docs/pdf_source_notes.md` |
| D-04 | DR-01 (`ref_file_manifest`: unique hash, parse status, error text) | One error text column | `error_text` says why a file was not parsed (rejected, duplicate, flagged, error) and is NULL on every parsed file. Parse warnings on a parsed file go in a new column `warning_text`, `"; "`-separated, without the former `warning:` prefix. Examples: 2023-10383 (`base_schedules_prefixed`), 2024-10569 (`summary_date_differs`), 2024-10691 (`price_not_provided`), 2025-12566 (`overflow_text_reassigned`). The `01b` review display lists `parse_status != 'parsed' OR warning_text IS NOT NULL`. DR-01 is a new PDF-path table, so the frozen `mart_bid_analysis` contract (FR-40) is not affected. | Hogan, 2026-10-09 | `src/bidtab_pipeline/contracts/__init__.py` (`REF_FILE_MANIFEST`), `src/bidtab_pipeline/sources/pdf/manifest.py`, `src/bidtab_pipeline/sources/pdf/bronze.py`, `notebooks/01b_parse_pdf_bidtab.py`, `tests/unit/pdf/test_pdf_ingest.py` |

## BRD v0.2 ID changes that affect this repository

| v0.2 ID | Change from v0.1 | Effect here |
|---|---|---|
| FR-04, FR-05 | Now MVP-B (Track B): SharePoint intake under a naming convention, read through the SharePoint-to-Databricks connection | No code. Track A keeps the landing volume (FR-01, `Settings.pdf_landing`) |
| FR-17 | Now MVP-B: parse per-bidder PlanetBids PDFs into DR-02, with written line and bid totals | No code until bidder PDF samples arrive (v0.2 open question 2). DR-02 stays the ingestion interface |
| FR-22 | Records the as-built key: `bid_type`, EAN, item number, contractor canonical name; adding source file and solicitation number is a future change | Matches `04` line 31 and backlog B-13; the refactor reproduces it unchanged |
| FR-14, FR-21, DR-01 | Amended in the requirement text | D-02, D-03, D-04 above |
| Appendix A | Deviation log D-01 to D-04 | This file |
| Appendix B | As-built findings B-10 to B-13 | `docs/backlog.md` (B-01 to B-13; B-01 to B-09 are not in the BRD) |
