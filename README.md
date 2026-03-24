# PDX Bid Tabs Pipeline

This codebase exists to turn raw Port of Portland bid tab workbooks into a dependable analytical dataset for bid history review.

The main goal is to ingest, clean, standardize, and transform raw bid tab data into a canonical enriched fact table with one row per:
- project
- base or alternate scope
- pay item
- bidder

That fact table is the primary analytical product. Supporting dimension tables are derived from it for project, scope, bidder, and pay item context.

The repo is intentionally being structured so the core pipeline can be reused in local scripts today and migrated into Databricks notebooks later with minimal translation.

## What This Repo Is For
- building a trustworthy historical bid dataset from messy Excel bid tabs
- preserving traceability back to source workbook, sheet, and row
- supporting reviewer-friendly validation of parsing and transformation logic
- producing a fact-first model that can feed downstream reporting and dashboard work

## What This Repo Is Not For
- ad hoc one-off analysis as the primary codebase purpose
- hiding business logic inside many unrelated top-level scripts
- making report artifacts the main contract instead of the core fact model

## Core Stages
- `bidtabs extract`
  - Reads raw bid tab workbooks from `data_in/`
  - Writes staging outputs:
    - `data_out/compiled_excel_itemized_raw_snapshot.csv`
    - `data_out/compiled_excel_itemized_clean.csv`
- `bidtabs build-model`
  - Builds the canonical analytical model from the clean staging extract
  - Writes:
    - `data_out/fact_bid_item_enriched.csv`
    - `data_out/dim_project.csv`
    - `data_out/dim_scope.csv`
    - `data_out/dim_bidder.csv`
    - `data_out/dim_pay_item.csv`
  - Also writes compatibility exports:
    - `data_out/Projects.csv`
    - `data_out/Items.csv`
    - `data_out/Bids.csv`
- `bidtabs build-reports`
  - Builds optional report artifacts from staged/core outputs

## Source Layout
- `src/bidtabs/extract.py`: workbook ingestion and staging extract builders
- `src/bidtabs/model.py`: canonical fact/dimension builders and compatibility exports
- `src/bidtabs/reporting.py`: optional reporting facade
- `src/bidtabs/cli.py`: 3-stage CLI entrypoint

## Local Compatibility
- Existing `scripts/*.py` entrypoints remain callable for compatibility.
- New development should import from `bidtabs.*` instead of importing business logic from `scripts.*`.

## Databricks Mapping
- Notebook 1: build raw snapshot
- Notebook 2: build clean staging extract and QA outputs
- Notebook 3: build canonical fact and dimensions
- Optional Notebook 4: build report artifacts

The intended notebook pattern is: load data/config tables, call pure library functions, then write outputs.
