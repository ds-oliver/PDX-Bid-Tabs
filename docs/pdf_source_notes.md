# PDF source notes (Phase 3)

**Status 2026-10-07:** Phase 3 gate accepted on the 17 fixtures. No unseen PDF
exists yet (2026-13405 turned out to be a workbook), so there is no holdout
result. If an unseen PDF is supplied under `local_inputs/holdout/`, it is run
once and the result is appended below.

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
| 2025-12566 | Item 0056's fourth description line "(Section 344300)" does not fit its cell. The page clips it (invisible), but the text layer keeps it 1.4 pt above item 0057's first line, which garbled 0057 ("A(Sdejucstito En x3is4t4in3g0 0T)axiway ...") and dropped 0056's spec reference. Found by the Phase 4a dry run (crosswalk misses), on pages 6 and 12 | The line is moved back to the row above only when it sits exactly one line pitch below that row's last line (within 0.6 pt), in the description column; each repair is a warning. Any other overlapping text is flagged (`overlapping_text`). No other cell in the 17 fixtures overlaps |
| Several | Kerning gaps in the text layer ("Acme Concrete P aving, Inc.") | Bidders matched on a key without spaces or punctuation; raw text kept |
| 2018-7876 | Spec references like "Item GP-50" | FAA under the amended FR-14 pattern `Item [A-Z]{1,2}-\d{2,3}` (docs/brd_deviations.md D-02). Across the 17 fixtures every spec reference is now FAA or PORT; none is UNK |

## Provisional choices for Phase 4

- **bid_type.** Mapped to the workbook sheet names so the shared Silver SQL
  classifies tabs the same way: `Base Bid Tab`, `Alternate Bid Tab`, or
  `Alternate Bid Tab <n>` when there are several alternates; `Base Bid Tab -
  <schedule>` when a project has several base schedules (2023-10383). Whether
  production's renamed workbooks use these names is unknown; the parity report
  must check it, since `natural_key` includes `bid_type`.

### bid_type for several base schedules: check against the xlsx (Phase 4a follow-up)

Sources: the May 14 v4 exports in `local_inputs/provisional/databricks_v4_2026-05-14`
(Bronze, Silver, mart) and reference `01_parse_single_bidtab.py`. The two workbooks
themselves were not opened.

| Workbook | EAN | Solicitation | Distinct `bid_type` in the May 14 mart | Item numbers |
|---|---|---|---|---|
| Taxiway T Bid Tab.xlsx | 2018D027 | 2019-8247 | `Base Bid Tab` (66 items, 330 rows), `Alternate Bid Tab` (43 items, 215 rows) | `0001`-`0066` and `0001`-`0043`, one run per sheet |
| PDX_2021D007 Bid Tab.xlsx | 2021D007 | 2022-9477 | `Base Bid Tab` (18 items, 36 rows), `Alternate Bid Tab` (1 item, 2 rows) | `1-001`-`1-018` and `2-001`: a prefix per sheet (`1-` base, `2-` alternate), the only prefixed numbering in the mart |

Neither workbook has a schedule marker in Bronze (`is_section_header` is FALSE on every
row, see B-08), and neither EAN is among the 17 PDFs.

Across the whole May 14 mart `bid_type` takes six values only: `Base Bid Tab`,
`Alternate Bid Tab`, `Alternate Bid Tab 1` to `4`. That is by construction: `01` reads only
the sheets in `CANONICAL_SHEETS` (lines 35-42), and `CANONICAL_BID_TYPE_RE` (line 54) is
`^(Base Bid Tab|Alternate Bid Tab(?: \d+)?)$`. A workbook with several base schedules has
them on the one `Base Bid Tab` sheet, kept apart by item numbering.

Multiple-base-schedule form among the 17 PDFs: one file only.

| PDF | EAN | Schedule | Current PDF `bid_type` |
|---|---|---|---|
| 2023-10383 | 2022D024 | Bid Schedule A (79 items) | `Base Bid Tab - Bid Schedule A` |
| | | Bid Schedule B (60 items) | `Base Bid Tab - Bid Schedule B` |
| | | Additive Alternate 1 (5 items) | `Alternate Bid Tab 1` |
| | | Additive Alternate 2 (5 items) | `Alternate Bid Tab 2` |

**The base naming does not match the xlsx pattern.** `Base Bid Tab - <schedule>` is
outside the six values `01` can produce. Silver would still class it `BASE` (`LIKE
'%Alternate%'` is false), but anything that filters on `bid_type = 'Base Bid Tab'` would
miss it, and the value is new to `natural_key`. The alternate naming (`Alternate Bid Tab
<n>`, and `Alternate Bid Tab` for a single one) does match.

Item numbers in 2023-10383 restart in each schedule: A is `0001`-`0079`, B is
`0001`-`0060`, so 60 item numbers occur in both. Mapping both schedules to `Base Bid Tab`
with the printed item numbers would give 60 colliding `natural_key` values
(`bid_type~ean~item_no`).

**Proposed mapping (not implemented; it feeds `natural_key`, so it waits for approval).**
Follow the prefixed numbering 2021D007 uses:

- every base schedule gets `bid_type = 'Base Bid Tab'`;
- when a file has more than one base schedule, prefix `item_no` with the schedule's letter
  or number from its label (`Bid Schedule A` item `0001` becomes `A-0001`); with one base
  schedule, `item_no` stays as printed;
- alternates unchanged;
- `source_sheet` keeps the PDF schedule label, so the original schedule and item number
  can still be recovered.

Trade-off: `A-0001` is a number the PDF does not print, and nobody can check yet whether
production's workbook for 2022D024 numbers the schedules this way; the May 14 mart does not
contain 2022D024. The alternative, keeping a distinct `bid_type` per base schedule, leaves
`item_no` as printed but adds `bid_type` values the xlsx path never produces.
- **source_sheet** holds the PDF schedule label (PDFs have no sheets).
- **Descriptions** join wrapped lines with single spaces and keep the spec
  reference, as 01's cleanup does to a workbook cell. A line break after a
  hyphen would become "- " in the PDF; the parity report should look for
  crosswalk misses of this kind.
