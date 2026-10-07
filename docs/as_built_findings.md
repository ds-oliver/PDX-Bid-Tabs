# As-built findings: PDX-Bid-Tabs repository vs BRD Section 3

**Prepared:** 2026-10-06 | **Branch:** `feature/pdf-source` | **Spec:** `docs/BidTab_PDF_Ingestion_BRD.md`

## 1. Repository baseline

| Item | Value |
|---|---|
| Remote | `https://github.com/ds-oliver/PDX-Bid-Tabs.git` |
| Branches on remote | `main` only (also the default branch, `origin/HEAD -> origin/main`) |
| Branched from | `main` |
| Latest commit on `main` | `ed7adbddfbc7159d76da4f23c26de37937794238` |
| Commit date | 2026-03-23 17:38:11 -0700 (author `ds-oliver`) |
| Commit message | "Revise README to clarify the purpose and structure of the PDX Bid Tabs Pipeline…" |
| History | 6 commits, 2026-02-10 to 2026-03-23 |
| Commits added on this branch so far | `ede5f89` BRD in `docs/`; `d25b519` PDF fixtures in `tests/fixtures/pdf/` |

## 2. Headline finding

**The repository does not contain the Databricks pipeline in BRD Section 3.** It has no notebooks
01 to 05, no Spark or Unity Catalog code, and no tables named `bronze_raw_rows`,
`silver_bid_items`, `int_crosswalk`, or `mart_bid_analysis`.

The repository is a local pandas/openpyxl Python package (`src/bidtabs`) with a 3-stage CLI. It
reads workbooks from `data_in/` and writes CSVs to `data_out/` and `reports/`. The README says
it is structured to be "migrated into Databricks notebooks later". Its last commit
(2026-03-23) predates the Databricks notebook build: local notebook exports elsewhere are dated
May 2026, and the Databricks table exports are dated 2026-05-14. Section 4 compares those exports.

So **Step 4 of the task cannot be done as written against this repository.** It asks to
parameterize notebooks 02 to 04, which are not in Git. See Section 8 for the decisions needed.

## 3. Notebook names and stages: BRD vs repository

| BRD Section 3 | Repository equivalent | Match? |
|---|---|---|
| `01` parses workbooks → `bronze_raw_rows` | `bidtabs extract` → `build_raw_snapshot()` → `data_out/compiled_excel_itemized_raw_snapshot.csv` | Stage exists; different name, format, and columns |
| `02` cleans → `silver_bid_items` | `bidtabs extract` → `build_clean_extract()` → `data_out/compiled_excel_itemized_clean.csv` | Stage exists in the same CLI command as 01; different columns |
| `03` loads crosswalk → `int_crosswalk` | None in the core pipeline. `scripts/build_estimate_item_crosswalk.py` (via `bidtabs build-reports`) is a fuzzy, spec-anchored *report* against the One Port Estimating catalog | **No** |
| `04` builds `mart_bid_analysis` + `crosswalk_unmapped_items` view | `bidtabs build-model` → `fact_bid_item_enriched.csv` + `dim_project/scope/bidder/pay_item.csv` + compatibility `Projects/Items/Bids.csv` | Different model (star schema, no crosswalk join) |
| `05` exports CSV snapshots | All stages write CSV; no separate export step | No equivalent stage |
| Job `bidtab_pipeline_full_refresh` | None. Run manually through the CLI | **No** |
| Landing `/Volumes/pop-poc/bidtab/source_files/` | `./data_in/` (workbooks committed to Git) | **No** |
| Config in `/Volumes/pop-poc/bidtab/config/` | `./config/*.csv` | Different files (Section 6) |

The README also lists a planned Databricks layout (4 notebooks: raw snapshot, clean staging + QA,
fact + dims, reports). That layout does not match the BRD's 01 to 05 either.

## 4. Table names and column lists

### 4a. Repository (code on `main`)

**Bronze-equivalent: `compiled_excel_itemized_raw_snapshot.csv`** (`extract.py:RAW_SNAPSHOT_COLUMNS`, 22 columns, all strings)
`source_file, source_sheet, source_row_index, source_table_header_row, project_ean, solicitation_no,
letting_date_raw, location_name_raw, project_name_raw, bid_schedule_name, bid_schedule_type,
bid_schedule_code, line_no, item_description_raw, quantity_raw, unit_code_raw, unit_price_raw,
total_price_raw, bidder_name_raw, is_totals_row, totals_row_label, schedule_total_raw`

**Silver-equivalent: `compiled_excel_itemized_clean.csv`** (`schemas.py:COMPILED_COLUMNS`, schema_version 2.1, 42 columns)
`schema_version, extract_run_id, source_file, source_sheet, source_row_index, source_table_header_row,
project_ean, solicitation_no, letting_date_raw, letting_date, location_name_raw, project_name_raw,
bid_schedule_name, bid_schedule_type, bid_schedule_code, line_no, item_description_raw,
item_description_clean, item_code_raw, item_code_norm, section_code_raw, section_code_norm, quantity,
unit_code_raw, unit_code_norm, bidder_name_raw, bidder_name_canonical, bidder_type,
is_engineers_estimate, unit_price, total_price, total_price_calc, price_valid_flag, parse_confidence,
is_totals_row, totals_row_label, schedule_total, specification, alternate_specification,
pay_item_description, supplemental_description, item`

Grain: file × sheet × source row × bidder, **including schedule-total rows** (`is_totals_row`).

**int_crosswalk-equivalent:** none. The closest is the report output
`reports/estimate_item_crosswalk_detail.csv` / `_table.csv` / `_unmapped.csv`, built by fuzzy
matching to `data_in/DRAFT One Port Estimating - Quantities Tool.xlsx`. The core model does not
consume it.

**Mart-equivalent: `fact_bid_item_enriched.csv`** (`model.py:_build_fact`, 35 columns)
`project_id, scope_id, bidder_id, pay_item_id, extract_run_id, source_file, source_sheet,
source_row_index, parse_confidence, project_ean, solicitation_no, project_name_raw, letting_date,
location_name_raw, scope_type, scope_code, bid_schedule_name, bid_schedule_type, bid_schedule_code,
line_no, specification, alternate_specification, pay_item_description, supplemental_description, item,
quantity, unit_code_norm, bidder_name_canonical, bidder_type, is_engineers_estimate, unit_price,
total_price, price_valid_flag, is_winner, rank`

Grain: project × scope (BASE/ALT schedule) × pay item × bidder. Dimensions: `dim_project` (9 cols),
`dim_scope` (8), `dim_bidder` (5), `dim_pay_item` (9). `docs/data_model.md` names the compatibility
tables `Projects` (7 cols), `Items` (11), and `Bids` (7: `bid_id, item_id, contractor_name, unit_price,
total_price, is_winner, rank`) as "the production semantic model for Power BI".

### 4b. Databricks tables (not in Git; secondary evidence only)

These column lists come from CSV exports in the capstone shared drive
(`Data Files/Databricks Exports/v4/*.csv`, file dates 2026-05-14), not from notebook code. They
show what the BRD describes, but I cannot confirm they match what is deployed today.

| Table | Rows | Columns |
|---|---|---|
| `bronze_raw_rows` | 6,295 | `source_file, source_sheet, bid_type, ean, project_name, airport_name, solicitation_no, bid_date, item_no, item_description_raw, estimated_quantity, unit, contractor_name, contractor_position, unit_price, total_price, is_section_header, ingested_at, bronze_loaded_at` |
| `silver_bid_items` | 5,950 | `source_file, source_sheet, bid_type, tab_type, ean, project_name, airport_name, project_name_full, solicitation_no_raw, solicitation_no, bid_date, bid_year, item_no, item_no_sort, item_description_raw, item_description_clean, item_description_normalized, estimated_quantity, unit, unit_clean, contractor_name_clean, awarded_bidder_canonical, contractor_position, is_awarded_bid, unit_price, total_price, unit_price_null_flag, total_price_zero_flag, price_suspicious_flag, bronze_loaded_at, silver_loaded_at` |
| `int_crosswalk` | 780 | `item_description_raw, raw_join_key, item_description_normalized, catalog_cost_code_original, catalog_cost_code, catalog_cost_code_desc, catalog_division, faa_item_code, port_section_code, spec_type` |
| `mart_bid_analysis` | 5,950 | `bid_item_sk, natural_key, ean, project_name_full, project_name, airport_name, solicitation_no, bid_date, bid_year, source_file, bid_type, tab_type, item_no, item_no_sort, item_description_raw, item_description_normalized, catalog_item_description, estimated_quantity, unit, catalog_division, catalog_cost_code, catalog_cost_code_desc, catalog_cost_code_original, spec_type, crosswalk_confidence, faa_item_code, port_section_code, is_catalog_mapped, contractor_name_canonical, contractor_position, is_awarded_bid, unit_price, total_price, effective_unit_price, unit_price_null_flag, total_price_zero_flag, price_suspicious_flag, bronze_loaded_at, silver_loaded_at, mart_loaded_at` |
| `crosswalk_unmapped_items` | 0 | `item_description_raw, affected_row_count, affected_project_count, example_projects, latest_bid_year, latest_bid_date, suggested_action, report_generated_at` |

The mart in that export covers 27 source files. `PDX_2017D013.xlsx` is absent, which matches the BRD.

## 5. Where engineer's estimate rows are kept or dropped

| Layer | Repository (code) | Databricks export (May 14) | BRD Section 3 says |
|---|---|---|---|
| Bronze / raw snapshot | **Kept** (bidder column like any other) | **Absent.** No `contractor_name` contains "engineer" or "estimate" in 6,295 rows | not stated |
| Silver / clean extract | **Kept**, flagged `is_engineers_estimate = True`, `bidder_type = ENGINEERS_ESTIMATE`, `price_valid_flag = False` (`extract.py:classify_bidder`, `build_clean_extract`) | **Absent** | Silver keeps EE rows |
| Mart / fact | **Kept** in `fact_bid_item_enriched` with the flag. Excluded only from `is_winner` and `rank` (`model.py:_build_fact`) | **Absent** | Mart excludes EE rows |
| Compat `Bids.csv` | **Kept** (`is_winner = False`, blank rank) | n/a | n/a |

Detection is a name match: the bidder label contains both "engineer" and "estimate". The model
layer also flags any canonical name that contains "ENGINEER".

Schedule-total rows are kept in the clean extract (`is_totals_row`, `schedule_total`) and dropped
from the fact. `qa.py` reconciles them to the line-item sums, with tolerance of $5.00 or 2%.

## 6. Config files

| BRD Section 3 config (Volume) | In repository? | Repository config actually used |
|---|---|---|
| `Final_Recommended_Line_Item_List.csv` (crosswalk, key `item_description_raw`, case-insensitive trimmed) | **No** | None. Crosswalk is a fuzzy report against the One Port Estimating xlsx plus `config/estimate_item_mapping_rules.csv` (122 rules) and `config/estimate_item_catalog.csv` (114 items) |
| `contractor_alias_mapping.csv` | **No** | `config/contractor_name_map.csv` (2 rows, EE spellings only) plus suffix normalization in `normalize.py` |
| `AwardedBidsSearchList.xlsx` | **No** | None. "Winner" means lowest total per project (`is_winner`), not an awarded-bid join |
| `unit_mapping.csv` | **No** | None. Units are uppercased with spaces removed |
| `concat_fixes.csv` | **No** | `config/pay_item_parse_overrides.csv` (header only, no rules) plus hard-coded regex fixes in `parse_items.py` |
| `text_normalization.csv` | **No** | None |
| n/a | | Also present: `location_dictionary.csv` (19 rows), `spec_section_catalog.csv` (226 rows), `spec_mapping.csv` (empty placeholder) |

## 7. Differences from BRD Section 3

1. **No notebooks 01 to 05** and no Databricks code of any kind. The pipeline is a local Python CLI.
2. **No job.** `bidtab_pipeline_full_refresh` does not exist in the repository.
3. **Landing is `data_in/` in Git**, not `/Volumes/pop-poc/bidtab/source_files/`. 30 workbooks, including the One Port Estimating and OPC files (plus
   Office lock files) are committed.
4. **Table names differ:** CSV files (`compiled_excel_itemized_*`, `fact_bid_item_enriched`, `dim_*`,
   `Projects/Items/Bids`) rather than `bronze_raw_rows`, `silver_bid_items`, `int_crosswalk`, and
   `mart_bid_analysis`.
5. **No `int_crosswalk` stage and no `crosswalk_unmapped_items` view.** Crosswalking is an optional
   fuzzy-match report, not an exact `item_description_raw` join.
6. **None of the six BRD config files exist.** The repository uses different config (Section 6).
7. **No loader guardrails.** Nothing halts on invalid `spec_type`, duplicate raw description, or blank
   required field. `spec_type` does not exist. The analogue, `dim_pay_item.standard_cat`, uses
   `FAA | PDX | UNKNOWN`, not `FAA | PORT | UNK`. The only uniqueness check
   (`enforce_canonical_key_uniqueness`) logs duplicates and does not halt.
8. **Engineer's estimate handling is inverted at the mart.** The repository keeps EE rows in the fact.
   The BRD says the mart excludes them. The May export has no EE rows at any layer, which also
   contradicts the BRD's "Silver keeps them".
9. **Mart grain wording:** the repository fact is project × scope × pay item × bidder. That matches
   the BRD grain in substance, but the column names and contract are entirely different. FR-40
   ("same columns, types") cannot be checked against the repository.
10. **No `tab_type`, `solicitation_no_url`, `price_suspicious_flag`, `is_awarded_bid`, contractor
    aliasing, unit mapping, or unit-price backfill.** FR-20 to FR-22 and FR-42 name these as the
    Silver/mart behavior to reuse.
11. **Header parsing uses free-text regex** over the rows above the table header (`parse_header.py`),
    not fixed metadata rows 1 to 6 as the BRD describes. It still depends on the
    "Item No." header row and cached formula values (`load_workbook(data_only=True)`).
12. **Schedule type comes from the sheet title** (`"alt"` in the title → ALTERNATE). This is one of
    the workbook dependencies the BRD says the PDF path removes.
13. **Bidder identity:** the BRD Bronze export has `contractor_position`. The repository has no
    position column, only the bidder label scanned from up to 10 rows above.

## 8. Other findings that affect Steps 3 to 5

- **Overlap set is 8 solicitations, not 5.** Matching on solicitation number, the May mart export
  shares these with the PDF fixtures:

  | EAN | Solicitation | xlsx file | BRD lists? |
  |---|---|---|---|
  | 2023D003 | 2024-10481 | `PDX_2023D003.xlsx` | yes |
  | 2023D011 | 2023-10218 | `PDX_2023D011.xlsx` | yes |
  | 2023D028 | 2024-10569 | `PDX_2023D028.xlsx` | yes |
  | 2024D016 | 2025-12724 | `PDX_2024D016 - Bid Set Bid Tab.xlsx` | yes |
  | 2024D045 | 2024-10691 | `PDX_2024D045.xlsx` | yes |
  | 2023D016 | 2025-12566 | `PDX_2023D016.xlsx` | **no** |
  | 2023D018 | 2024-10519 | `HIO Runway and Taxway Seals Bid Tab.xlsx` | **no** |
  | 2023D025 | 2024-10566 | `PDX Lift Station Bid Tab.xlsx` | **no** |

- **17 PDFs, not 16.** All 17 in `Port Provided/Bid Tabs/` are compiled bid tabs with a text layer
  (3 to 31 pages; 16 Bluebeam, 1 Adobe PDF Library). File names use `YYYY-NNNNN Bid Tab.pdf`, not
  `20187876_Bid_Tab.pdf`. I added all 17 to `tests/fixtures/pdf/` rather than drop one arbitrarily.
  `2018-7876` is EAN 2017D013, the project excluded from the xlsx path, as the BRD says.
- **`spec_type` casing:** the May mart export uses `FAA`, `Port`, and `UNK`. The BRD guardrail and
  FR-14 say `PORT`.
- **Crosswalk coverage baseline:** the May mart export has `is_catalog_mapped = True` on all 5,950
  rows and an empty `crosswalk_unmapped_items`. "Coverage equals or exceeds xlsx" therefore means
  100%, but only against the deployed crosswalk CSV, which is not in this repository.
- **Existing tests:** on Python 3.12 with pandas 3.0.6 and openpyxl 3.1.5, 42 pass and 2 fail:
  `test_dashboard_field_mapping_artifacts` (`ModuleNotFoundError: scripts` when the subprocess runs
  a script) and `test_pay_item_similarity_artifacts` (`TypeError` in a pandas `map`, likely a
  pandas 3 change). `pyproject.toml` omits `xlsxwriter` and `rapidfuzz`, which the tests need.
- **Tests overwrite tracked files** in `reports/` (crosswalk CSVs and variability workbooks). I
  restored them after running. Any future test run needs the same care until this is fixed.
- **Repository hygiene:** 896 `.pycache/` files are committed. They include absolute paths from a
  previous machine. There are also 9 Office lock files (`~$*`). `build_estimate_item_crosswalk.py`
  hard-codes `/Users/hogan/BTA 525 Capstone/...` default paths.
- **Python version:** `pyproject.toml` requires Python 3.10 or later. The system Python here is 3.9.6,
  so I used a project-local `.venv` on Python 3.12 (now in `.gitignore`).

## 9. Decisions needed before Step 3

1. **Which pipeline is the xlsx baseline?** The Databricks notebooks the BRD describes are not in
   this repository. Options:
   a. Get the notebook source into Git (for example, Port IT or `ds-oliver` commits
      `/Workspace/Shared/Bidtab/Src/` to this repository or another one), then branch from that.
   b. Treat this repository's `bidtabs` package as the xlsx path. The PDF parser would then emit the
      `compiled_excel_itemized_clean` contract, and "reuse 02 to 04" would mean reusing `build_model`.
      Parity would be against `fact_bid_item_enriched`, not `mart_bid_analysis`. This conflicts
      with FR-30 and FR-40.
2. **Overlap set:** use the BRD's 5 EANs or all 8 that match on solicitation number?
3. **Fixtures:** keep all 17 PDFs, or name the one to exclude?
4. **EE in the mart:** the BRD (exclude), the repository (keep and flag), and the May export (absent
   everywhere) disagree. Which one is the reference behavior for parity?

The PDF extraction work (Step 3: `src/pdf_parser/`, the manifest, Bronze PDF tables, and fixture
tests) does not depend on decision 1. It can start once decisions 2 and 3 are settled. Steps 4 and 5
depend on decision 1.
