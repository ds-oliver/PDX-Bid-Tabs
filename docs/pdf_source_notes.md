# PDF source notes (Phase 3)

**Status 2026-10-07:** Phase 3 gate met on the 17 fixtures. Holdout (solicitation
2026-13405) not yet supplied; it runs once, at the gate, when it arrives.

## Results on the 17 fixtures

| Check | Result |
|---|---|
| Files parsed without unhandled errors | 17 of 17 (none flagged) |
| Summary totals reconciled within $1.00 (FR-50, bidder x summary schedule) | 149 of 149 |
| Detail total rows reconciled within $1.00 (schedule and roll-up totals) | 177 of 177 |
| Item rows (item x bidder x schedule) | 4,237 |
| Hand-checked against rendered pages | 2018-7876 (31 pages), 2023-10383 (31 pages), 2024-10564 (every value) |

The fixture set is 17 PDFs, not the BRD's 16: 16 are byte-identical to the BRD
samples, and 2025-12566 is the extra one (confirmed by Hogan by hash).
2018-7876 (EAN 2017D013) has no xlsx counterpart and is excluded from parity.

## Layout facts the parser relies on

- Page 1: summary table, header block above a `Bidder` row, Engineer's Estimate last.
- Detail pages: one ruled table each; up to three bidders per page; a schedule's
  pages repeat for each bidder group (alphabetical, Engineer's Estimate last);
  each run of pages ends with a `Total Amount ...` row.
- Roll-up totals follow a schedule total on the same page ("Base Bid and
  Additive Alternate A"; "Bid Schedules A and B (Basis of Award)" in
  2023-10383) and cover every schedule up to the one they close.
- Summary columns map to detail totals by role, not by label: the one base column
  to the single `(Basis of Award)` total, alternates in order (2024-10564 labels
  the alternate "1" on the summary and "A" on the detail page).

Anything else raises a flag with a reason code (`table_count`,
`header_block_unrecognized`, `column_header_unrecognized`,
`bidder_header_unrecognized`, `item_number_unrecognized`, `row_unrecognized`,
`amount_unrecognized`, `schedule_not_closed`, `schedule_items_differ`,
`schedule_missing_bidder_group`, `bidder_set_mismatch`,
`summary_schedule_mapping`, and others). A flagged file writes no rows.

## Source data findings

| File | Finding | Handling |
|---|---|---|
| 2024-10569 | Summary page date 2/9/2025; all six detail pages 2/4/2025 | Warning on the manifest; Bronze uses the detail-page date (the page each row comes from) |
| 2024-10691 | `*` means "Non-responsive to the bid submission requirements", not "Corrected Bid Total"; that bidder's 13 unit prices read "Not provided" | `is_corrected_total` false with the footnote kept; "Not provided" read as null, counted as a warning |
| 11 files | Starred totals marked "*Corrected Bid Total" | `is_corrected_total` true; detail item totals already reflect the correction (all reconcile) |
| Several | Kerning gaps in the text layer ("Acme Concrete P aving, Inc.") | Bidders matched on a key without spaces or punctuation; raw text kept |
| 2018-7876 | Spec references like "Item GP-50" | FR-14 types them UNK (pattern is `Item [A-Z]-\d{3}`) |

## Provisional choices for Phase 4

- **bid_type.** Mapped to the workbook sheet names so the shared Silver SQL
  classifies tabs the same way: `Base Bid Tab`, `Alternate Bid Tab`, or
  `Alternate Bid Tab <n>` when there are several alternates; `Base Bid Tab -
  <schedule>` when a project has several base schedules (2023-10383). Whether
  production's renamed workbooks use these names is unknown; the parity report
  must check it, since `natural_key` includes `bid_type`.
- **source_sheet** holds the PDF schedule label (PDFs have no sheets).
- **Descriptions** join wrapped lines with single spaces and keep the spec
  reference, as 01's cleanup does to a workbook cell. A line break after a
  hyphen would become "- " in the PDF; the parity report should look for
  crosswalk misses of this kind.
