# Data Model Overview

This project is an internal bid lookup tool: it parses Bid Tabulation Excel sheets into a clean analytical extract for historical analysis. It does not report selection outcomes.

## Primary Deliverable
- `compiled_excel_itemized_clean.csv`: canonical bidder-line extract (Project x Schedule x Line Item x Bidder), including totals rows.

## Analysis Schema (Derived from Bid Tab Sheets)
- `dim_project`: parsed sheet header fields.
- `dim_bid_schedule`: schedule identity inferred from sheet context.
- `dim_bidder`: bidder columns (contractors plus engineer's estimate if present).
- `dim_pay_item`: parsed item codes/sections and cleaned description.
- `dim_unit`: unit codes observed in sheets.
- `fact_bid_item_price`: bidder-level line item values.
- `fact_bid_schedule_total`: bidder-level schedule totals rows.

## Optional Tables (Flag-Gated)
- `dim_specification`, `bridge_pay_item_spec` with `--emit_spec_tables`.
- `fact_project_pay_item_metrics` with `--emit_metrics` via `scripts/build_metrics.py`.

## Dashboard Use (ODOT-Style Reference)
The end dashboard is designed for bid analytics similar to the ODOT example. These are the intended uses:
- Project/Schedule context: `dim_project`, `dim_bid_schedule` filter all visuals.
- Bidder comparisons: `dim_bidder` + `fact_bid_item_price` show bidder rankings and unit price comparisons.
- Line-item detail: `fact_bid_item_price` (unit/total) with `dim_pay_item` (description + `standard_cat`) for drill-down tables.
- Schedule totals: `fact_bid_schedule_total` for total bid comparisons per bidder.
- Optional metrics: `fact_project_pay_item_metrics` provides 3-low average and other bid-only summaries (flag-gated).

## ERD
```mermaid
erDiagram
  dim_project ||--o{ fact_bid_item_price : has
  dim_bid_schedule ||--o{ fact_bid_item_price : has
  dim_bidder ||--o{ fact_bid_item_price : has
  dim_pay_item ||--o{ fact_bid_item_price : has
  dim_unit ||--o{ fact_bid_item_price : uses
  dim_project ||--o{ fact_bid_schedule_total : has
  dim_bid_schedule ||--o{ fact_bid_schedule_total : has
  dim_bidder ||--o{ fact_bid_schedule_total : has
```
