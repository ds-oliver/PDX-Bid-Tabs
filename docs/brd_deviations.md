# Deviations from the BRD

Approved departures from `docs/BidTab_PDF_Ingestion_BRD.md` (local only). Each
entry names the BRD text, the change, who approved it, and where it lives.

| # | BRD reference | BRD says | Implemented | Approved | Where |
|---|---|---|---|---|---|
| D-01 | Section 4; Section 8 MVP exit criteria; Section 11 step 4 | 16 sample PDFs | 17 fixtures. 16 are byte-identical to the BRD samples; 2025-12566 is an additional compiled bid tab. Exit criteria apply to 17. 2018-7876 (EAN 2017D013) stays in parser tests and is excluded from parity, having no xlsx counterpart. | Hogan, 2026-10-07 (handoff Section 1, decision 3; hash check) | `tests/fixtures/pdf/`, `docs/pdf_source_notes.md` |
| D-02 | FR-14 | `spec_ref_type` is FAA when the reference matches `Item [A-Z]-\d{3}` | FAA pattern is `Item [A-Z]{1,2}-\d{2,3}`, so two-letter FAA items such as `(Item GP-50)` classify as FAA instead of UNK. PORT stays `Section \d{6}`; anything else is UNK. | Hogan, 2026-10-07 | `src/bidtab_pipeline/sources/pdf/detail.py` (`spec_ref_type`), `tests/unit/pdf/test_pdf_units.py` |
