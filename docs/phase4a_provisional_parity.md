# Phase 4a: provisional parity, PDF Bronze vs May 14 exports

> **Provisional.** Compared against the 2026-05-14 v4 Databricks exports, which predate the 2026-05-28
> baseline (no Engineer's Estimate rows; older code). Silver is not applied to the PDF rows. This is a
> dry run, not FR-51 and not a gate. Regenerate with `python tools/phase4a_provisional_parity.py`.

Matching: solicitation number between sources; schedules by `bid_type` (the PDF's provisional mapping);
bidders by a name key without spaces or punctuation, then the closest name (ratio at least 0.80).
The xlsx export has no Engineer's Estimate rows, so PDF Engineer's Estimate rows are left out of the
bidder and total comparisons and counted separately.

## Findings

- **Totals:** 59 of 59 bidder x schedule totals match within $1.00 across the 8 EANs.
- **Schedules:** the PDF's provisional `bid_type` names equal the xlsx `bid_type` values for every overlap EAN. No overlap EAN has several base schedules, so the `Base Bid Tab - <schedule>` form (2023-10383) is not exercised here.
- **Item and bidder counts per schedule:** equal (PDF Engineer's Estimate excluded).
- **Bidder names:** all matched; 1 by closest name rather than the exact key: 2025-12724: MJ Hughes Construction -> MJ HUGHES CONSTRUCTION INC (close, ratio 0.93).
- **Crosswalk coverage:** PDF 100.0% of rows vs xlsx 100.0%. This dry run found one parser defect, now fixed: a description line clipped on the page but present in the text layer (2025-12566 items 0056 and 0057; see docs/pdf_source_notes.md). 100% is expected: the PDFs are printed from the same compiled workbooks the crosswalk was built from, so this validates the FR-13 wrap-merge, not coverage of new solicitations. New-solicitation coverage is measured by FR-31 in Phase 4b.
- **Pullman SST (non-responsive, 2024-10691)** and the **single-bidder schedules** appear the same way on both sides; details below.

## Summary by solicitation

| Solicitation | EAN | BRD 5 | Schedules PDF | Schedules xlsx | Items PDF | Items xlsx | Bidders PDF (excl. EE) | Bidders xlsx | Bidder x schedule totals within $1 |
|---|---|---|---|---|---|---|---|---|---|
| 2024-10481 | 2023D003 | yes | 5 | 5 | 107 | 107 | 2 | 2 | 10/10 |
| 2023-10218 | 2023D011 | yes | 2 | 2 | 80 | 80 | 5 | 5 | 10/10 |
| 2024-10569 | 2023D028 | yes | 1 | 1 | 22 | 22 | 6 | 6 | 6/6 |
| 2025-12724 | 2024D016 | yes | 1 | 1 | 34 | 34 | 11 | 11 | 11/11 |
| 2024-10691 | 2024D045 | yes | 1 | 1 | 13 | 13 | 4 | 4 | 4/4 |
| 2025-12566 | 2023D016 | no | 2 | 2 | 70 | 70 | 5 | 5 | 10/10 |
| 2024-10519 | 2023D018 | no | 2 | 2 | 15 | 15 | 3 | 3 | 6/6 |
| 2024-10566 | 2023D025 | no | 2 | 2 | 50 | 50 | 1 | 1 | 2/2 |

Items are distinct item numbers summed over schedules.

## Crosswalk coverage

Share of rows whose `lower(trim(item_description_raw))` is in `int_crosswalk.raw_join_key` (May 14 export).
PDF descriptions are rebuilt per FR-13 (wrapped lines joined with single spaces, spec reference kept).
100% is expected because the PDFs are printed from the same compiled workbooks the crosswalk was built from. It validates the FR-13 wrap-merge, not coverage of new solicitations; that is measured by FR-31 in Phase 4b.

| Solicitation | EAN | PDF rows covered | PDF rows | xlsx rows covered | xlsx rows | PDF distinct descriptions covered |
|---|---|---|---|---|---|---|
| 2024-10481 | 2023D003 | 100.0% | 321 | 100.0% | 214 | 30/30 |
| 2023-10218 | 2023D011 | 100.0% | 480 | 100.0% | 400 | 70/70 |
| 2024-10569 | 2023D028 | 100.0% | 154 | 100.0% | 132 | 22/22 |
| 2025-12724 | 2024D016 | 100.0% | 408 | 100.0% | 374 | 34/34 |
| 2024-10691 | 2024D045 | 100.0% | 65 | 100.0% | 52 | 13/13 |
| 2025-12566 | 2023D016 | 100.0% | 420 | 100.0% | 350 | 63/63 |
| 2024-10519 | 2023D018 | 100.0% | 60 | 100.0% | 45 | 9/9 |
| 2024-10566 | 2023D025 | 100.0% | 100 | 100.0% | 50 | 35/35 |
| **All 8** | | **100.0%** | 2008 | **100.0%** | 1617 | |

### Top unmatched PDF descriptions

None: every PDF description for the 8 EANs is a crosswalk key.

## Non-responsive bidder in 2024-10691 (Pullman SST, Inc.)

| | PDF Bronze | xlsx mart (May 14) |
|---|---|---|
| Rows | 13 | 13 |
| Rows with null unit price | 13 | 13 |
| Sum of item totals | $945,062.70 | $945,062.70 |
| Name | Pullman SST, Inc. | PULLMAN SST INC |
| Summary total, footnote | $945,062.70, "*Non-responsive to the bid submission requirements of this solicitation" (is_corrected_total false) | not carried |

## Single-bidder schedules

Backlog B-10: workbook 01 skips any sheet with fewer than two Unit Price / Total Price pairs. The PDF
parser does not copy that skip. Schedules with exactly one contractor (Engineer's Estimate not counted):

| Solicitation | Schedule | In overlap set | xlsx rows for this schedule | Note |
|---|---|---|---|---|
| 2024-10564 | Alternate Bid Tab | no | — | No xlsx counterpart in the overlap set |
| 2024-10564 | Base Bid Tab | no | — | No xlsx counterpart in the overlap set |
| 2024-10566 | Alternate Bid Tab | yes | 25 | One contractor plus the Engineer's Estimate gives two price pairs, so 01 parses the sheet |
| 2024-10566 | Base Bid Tab | yes | 25 | One contractor plus the Engineer's Estimate gives two price pairs, so 01 parses the sheet |

## Per-solicitation detail

### 2024-10481 (EAN 2023D003) — in the BRD 5

PDF file `2024-10481 Bid Tab.pdf`; xlsx file `PDX_2023D003.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Alternate Bid Tab 1 | 25 | 25 | 2 | 2 |
| Alternate Bid Tab 2 | 19 | 19 | 2 | 2 |
| Alternate Bid Tab 3 | 20 | 20 | 2 | 2 |
| Alternate Bid Tab 4 | 22 | 22 | 2 | 2 |
| Base Bid Tab | 21 | 21 | 2 | 2 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| Fortis Construction, Inc. | FORTIS CONSTRUCTION INC | exact | Alternate Bid Tab 1 | $2,405,600.23 | $2,405,600.23 | match |
| Fortis Construction, Inc. | FORTIS CONSTRUCTION INC | exact | Alternate Bid Tab 2 | $2,840,799.44 | $2,840,799.44 | match |
| Fortis Construction, Inc. | FORTIS CONSTRUCTION INC | exact | Alternate Bid Tab 3 | $841,079.71 | $841,079.71 | match |
| Fortis Construction, Inc. | FORTIS CONSTRUCTION INC | exact | Alternate Bid Tab 4 | $518,802.99 | $518,802.99 | match |
| Fortis Construction, Inc. | FORTIS CONSTRUCTION INC | exact | Base Bid Tab | $6,387,362.33 | $6,387,362.33 | match |
| Northeast Electric, LLC | NORTHEAST ELECTRIC LLC | exact | Alternate Bid Tab 1 | $2,275,969.00 | $2,275,969.00 | match |
| Northeast Electric, LLC | NORTHEAST ELECTRIC LLC | exact | Alternate Bid Tab 2 | $2,580,308.00 | $2,580,308.00 | match |
| Northeast Electric, LLC | NORTHEAST ELECTRIC LLC | exact | Alternate Bid Tab 3 | $411,573.00 | $411,573.00 | match |
| Northeast Electric, LLC | NORTHEAST ELECTRIC LLC | exact | Alternate Bid Tab 4 | $382,289.00 | $382,289.00 | match |
| Northeast Electric, LLC | NORTHEAST ELECTRIC LLC | exact | Base Bid Tab | $7,573,242.00 | $7,573,242.00 | match |

PDF Engineer's Estimate rows left out: 107.

### 2023-10218 (EAN 2023D011) — in the BRD 5

PDF file `2023-10218 Bid Tab.pdf`; xlsx file `PDX_2023D011.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Alternate Bid Tab | 11 | 11 | 5 | 5 |
| Base Bid Tab | 69 | 69 | 5 | 5 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| Coffman Excavation | COFFMAN EXCAVATION | exact | Alternate Bid Tab | $402,928.00 | $402,928.00 | match |
| Coffman Excavation | COFFMAN EXCAVATION | exact | Base Bid Tab | $9,624,346.25 | $9,624,346.25 | match |
| Granite Construction Company | GRANITE CONSTRUCTION COMPANY | exact | Alternate Bid Tab | $417,263.04 | $417,263.04 | match |
| Granite Construction Company | GRANITE CONSTRUCTION COMPANY | exact | Base Bid Tab | $10,277,995.68 | $10,277,995.68 | match |
| K&E Excavating, Inc. | K&E EXCAVATING INC | exact | Alternate Bid Tab | $445,607.50 | $445,607.50 | match |
| K&E Excavating, Inc. | K&E EXCAVATING INC | exact | Base Bid Tab | $9,569,824.55 | $9,569,824.55 | match |
| Kerr Contractors Oregon, LLC | KERR CONTRACTORS OREGON LLC | exact | Alternate Bid Tab | $364,091.75 | $364,091.75 | match |
| Kerr Contractors Oregon, LLC | KERR CONTRACTORS OREGON LLC | exact | Base Bid Tab | $9,285,859.15 | $9,285,859.15 | match |
| Tapani, Inc. | TAPANI INC | exact | Alternate Bid Tab | $428,765.00 | $428,765.00 | match |
| Tapani, Inc. | TAPANI INC | exact | Base Bid Tab | $8,991,000.00 | $8,991,000.00 | match |

PDF Engineer's Estimate rows left out: 80.

### 2024-10569 (EAN 2023D028) — in the BRD 5

PDF file `2024-10569 Bid Tab.pdf`; xlsx file `PDX_2023D028.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Base Bid Tab | 22 | 22 | 6 | 6 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| Brix Paving Northwest, Inc. | BRIX PAVING NORTHWEST INC | exact | Base Bid Tab | $883,359.00 | $883,359.00 | match |
| Dirt & Aggregate Interchange | DIRT & AGGREGATE INTERCHANGE | exact | Base Bid Tab | $1,036,363.00 | $1,036,363.00 | match |
| Kerr Contractors Oregon, LLC | KERR CONTRACTORS OREGON LLC | exact | Base Bid Tab | $924,030.00 | $924,030.00 | match |
| Knife River Corporation - Northwest | KNIFE RIVER CORPORATION - NORTHWEST | exact | Base Bid Tab | $837,843.50 | $837,843.50 | match |
| Kodiak Pacific Construction | KODIAK PACIFIC CONSTRUCTION | exact | Base Bid Tab | $790,790.00 | $790,790.00 | match |
| Pacific Excavation, Inc. | PACIFIC EXCAVATION INC | exact | Base Bid Tab | $997,000.00 | $997,000.00 | match |

PDF Engineer's Estimate rows left out: 22.

### 2025-12724 (EAN 2024D016) — in the BRD 5

PDF file `2025-12724 Bid Tab.pdf`; xlsx file `PDX_2024D016 - Bid Set Bid Tab.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Base Bid Tab | 34 | 34 | 11 | 11 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| Apex Mechanical LLC | APEX MECHANICAL LLC | exact | Base Bid Tab | $4,249,540.76 | $4,249,540.75 | match |
| Coffman Excavation | COFFMAN EXCAVATION | exact | Base Bid Tab | $3,725,047.10 | $3,725,047.10 | match |
| Goodfellow Bros. LLC | GOODFELLOW BROS LLC | exact | Base Bid Tab | $4,508,106.50 | $4,508,106.50 | match |
| Interlaken, Inc. | INTERLAKEN INC | exact | Base Bid Tab | $4,186,136.00 | $4,186,136.00 | match |
| K&E Excavating, Inc. | K&E EXCAVATING INC | exact | Base Bid Tab | $3,389,211.50 | $3,389,211.50 | match |
| Kerr Contractors Oregon, LLC | KERR CONTRACTORS OREGON LLC | exact | Base Bid Tab | $4,894,385.30 | $4,894,385.30 | match |
| Landis+Landis Construction, LLC | LANDIS+LANDIS CONSTRUCTION LLC | exact | Base Bid Tab | $4,444,240.20 | $4,444,240.20 | match |
| MJ Hughes Construction | MJ HUGHES CONSTRUCTION INC | close, ratio 0.93 | Base Bid Tab | $4,826,299.00 | $4,826,299.00 | match |
| Moore Excavation, Inc. | MOORE EXCAVATION INC | exact | Base Bid Tab | $3,317,066.00 | $3,317,066.00 | match |
| Nutter Corporation | NUTTER CORPORATION | exact | Base Bid Tab | $2,940,525.00 | $2,940,525.00 | match |
| Tapani Inc. | TAPANI INC | exact | Base Bid Tab | $3,079,845.80 | $3,079,845.80 | match |

PDF Engineer's Estimate rows left out: 34.

### 2024-10691 (EAN 2024D045) — in the BRD 5

PDF file `2024-10691 Bid Tab.pdf`; xlsx file `PDX_2024D045.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Base Bid Tab | 13 | 13 | 4 | 4 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| Acme Concrete Paving, Inc. | ACME CONCRETE PAVING INC | exact | Base Bid Tab | $1,347,131.50 | $1,347,131.50 | match |
| C.R. Contracting, LLC | CR CONTRACTING LLC | exact | Base Bid Tab | $681,107.10 | $681,107.10 | match |
| Pullman SST, Inc. | PULLMAN SST INC | exact | Base Bid Tab | $945,062.70 | $945,062.70 | match |
| Roger Langeliers Construction Co. | ROGER LANGELIERS CONSTRUCTION CO. | exact | Base Bid Tab | $697,331.80 | $697,331.80 | match |

PDF Engineer's Estimate rows left out: 13.

### 2025-12566 (EAN 2023D016)

PDF file `2025-12566 Bid Tab.pdf`; xlsx file `PDX_2023D016.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Alternate Bid Tab | 9 | 9 | 5 | 5 |
| Base Bid Tab | 61 | 61 | 5 | 5 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| K&E Excavating, Inc. | K&E EXCAVATING INC | exact | Alternate Bid Tab | $218,040.40 | $218,040.40 | match |
| K&E Excavating, Inc. | K&E EXCAVATING INC | exact | Base Bid Tab | $7,448,777.00 | $7,448,777.00 | match |
| Kerr Contractors Oregon, LLC | KERR CONTRACTORS OREGON LLC | exact | Alternate Bid Tab | $168,668.55 | $168,668.55 | match |
| Kerr Contractors Oregon, LLC | KERR CONTRACTORS OREGON LLC | exact | Base Bid Tab | $6,129,171.00 | $6,129,171.00 | match |
| Kodiak Pacific Construction | KODIAK PACIFIC CONSTRUCTION | exact | Alternate Bid Tab | $211,109.00 | $211,109.00 | match |
| Kodiak Pacific Construction | KODIAK PACIFIC CONSTRUCTION | exact | Base Bid Tab | $6,588,047.00 | $6,588,047.00 | match |
| Tapani Inc. | TAPANI INC | exact | Alternate Bid Tab | $332,136.25 | $332,136.25 | match |
| Tapani Inc. | TAPANI INC | exact | Base Bid Tab | $6,624,793.00 | $6,624,793.00 | match |
| Western United Civil Group LLC | WESTERN UNITED CIVIL GROUP LLC | exact | Alternate Bid Tab | $237,385.25 | $237,385.25 | match |
| Western United Civil Group LLC | WESTERN UNITED CIVIL GROUP LLC | exact | Base Bid Tab | $6,537,599.00 | $6,537,599.00 | match |

PDF Engineer's Estimate rows left out: 70.

### 2024-10519 (EAN 2023D018)

PDF file `2024-10519 Bid Tab.pdf`; xlsx file `HIO Runway and Taxway Seals Bid Tab.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Alternate Bid Tab | 6 | 6 | 3 | 3 |
| Base Bid Tab | 9 | 9 | 3 | 3 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| American Road Maintenance | AMERICAN ROAD MAINTENANCE | exact | Alternate Bid Tab | $34,490.00 | $34,490.00 | match |
| American Road Maintenance | AMERICAN ROAD MAINTENANCE | exact | Base Bid Tab | $911,020.00 | $911,020.00 | match |
| C.R. Contracting, LLC | CR CONTRACTING LLC | exact | Alternate Bid Tab | $39,806.00 | $39,806.00 | match |
| C.R. Contracting, LLC | CR CONTRACTING LLC | exact | Base Bid Tab | $1,236,869.00 | $1,236,869.00 | match |
| Specialized Pavement Marking, LLC | SPECIALIZED PAVEMENT MARKING LLC | exact | Alternate Bid Tab | $52,801.20 | $52,801.20 | match |
| Specialized Pavement Marking, LLC | SPECIALIZED PAVEMENT MARKING LLC | exact | Base Bid Tab | $1,314,785.00 | $1,314,785.00 | match |

PDF Engineer's Estimate rows left out: 15.

### 2024-10566 (EAN 2023D025)

PDF file `2024-10566 Bid Tab.pdf`; xlsx file `PDX Lift Station Bid Tab.xlsx`.

| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |
|---|---|---|---|---|
| Alternate Bid Tab | 25 | 25 | 1 | 1 |
| Base Bid Tab | 25 | 25 | 1 | 1 |

| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |
|---|---|---|---|---|---|---|
| MJ Hughes Construction, Inc. | MJ HUGHES CONSTRUCTION INC | exact | Alternate Bid Tab | $924,860.00 | $924,860.00 | match |
| MJ Hughes Construction, Inc. | MJ HUGHES CONSTRUCTION INC | exact | Base Bid Tab | $837,232.50 | $837,232.50 | match |

PDF Engineer's Estimate rows left out: 50.
