#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.schemas import COMPILED_COLUMNS, STAR_SCHEMAS


def _table_md(columns):
    lines = ["| Column | Type | Nullable | Definition | Extraction Rule |", "|---|---|---|---|---|"]
    for c in columns:
        lines.append(f"| {c.name} | {c.dtype} | {c.nullable} | {c.description} | {c.source_rule} |")
    return "\n".join(lines)


def write_data_model(doc_dir: Path):
    text = """# Data Model Overview

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
"""
    (doc_dir / "data_model.md").write_text(text)


def write_compiled_dictionary(doc_dir: Path):
    intro = """# Data Dictionary: compiled_excel_itemized_clean.csv (v2)

## Totals Row Behavior
- Totals rows are identified when `item_description_raw` contains `Total Amount` or the phrase `Basis of Bid` (sheet text, case-insensitive).
- Totals rows are emitted one row per bidder with `is_totals_row=True`.
- For totals rows, `line_no`, `quantity`, `unit_code_*`, and `unit_price` are expected to be blank/null unless explicitly present.
- `schedule_total` stores the bidder-specific totals value from the totals row (bid total from sheet).

## Dashboard Use
- Filters/labels: `project_name_raw`, `letting_date`, `bid_schedule_type`, `bid_schedule_code`.
- Bidder comparisons: `bidder_name_canonical`, `bidder_type`.
- Line-item tables: `line_no`, `item_description_clean`, `quantity`, `unit_code_norm`, `unit_price`, `total_price`.
- Totals panels: `schedule_total` from totals rows (`is_totals_row=True`).

## Columns
"""
    body = _table_md(COMPILED_COLUMNS)
    (doc_dir / "data_dictionary_compiled_excel_itemized_clean_v2.md").write_text(intro + "\n" + body + "\n")


def write_analysis_dictionary(doc_dir: Path):
    required_tables = [
        "dim_project",
        "dim_bid_schedule",
        "dim_bidder",
        "dim_pay_item",
        "dim_unit",
        "fact_bid_item_price",
        "fact_bid_schedule_total",
    ]
    optional_tables = ["dim_specification", "bridge_pay_item_spec", "fact_project_pay_item_metrics"]

    lines = [
        "# Data Dictionary: Analysis Schema",
        "",
        "Derived convenience tables built from `compiled_excel_itemized_clean.csv`.",
        "",
        "## Required Tables (default)",
    ]
    for name in required_tables:
        lines.append(f"### {name}")
        lines.append(_table_md(STAR_SCHEMAS[name]))
        lines.append("")

    lines.append("## Optional Tables (default off)")
    lines.append("- Enable `dim_specification` and `bridge_pay_item_spec` with `--emit_spec_tables`.")
    lines.append("- Enable `fact_project_pay_item_metrics` with `--emit_metrics`.")
    lines.append("")

    for name in optional_tables:
        if name in STAR_SCHEMAS:
            lines.append(f"### {name}")
            lines.append(_table_md(STAR_SCHEMAS[name]))
            lines.append("")

    lines.append("## Example Join")
    lines.append("```sql")
    lines.append(
        "SELECT p.project_name, s.schedule_name, b.bidder_name_canonical, i.item_desc_canonical, f.total_price\n"
        "FROM fact_bid_item_price f\n"
        "JOIN dim_project p ON p.project_id = f.project_id\n"
        "JOIN dim_bid_schedule s ON s.bid_schedule_id = f.bid_schedule_id\n"
        "JOIN dim_bidder b ON b.bidder_id = f.bidder_id\n"
        "JOIN dim_pay_item i ON i.pay_item_id = f.pay_item_id;"
    )
    lines.append("```")

    lines.append("")
    lines.append("## Dashboard Measure Guidance (ODOT-Style)")
    lines.append("- Bidder total comparison: `fact_bid_schedule_total.schedule_total` by `dim_bidder` (exclude engineer estimate).")
    lines.append("- Unit price comparison: `fact_bid_item_price.unit_price` by `dim_bidder` and `dim_pay_item`.")
    lines.append("- Total price comparison: `fact_bid_item_price.total_price` by `dim_bidder` and `dim_pay_item`.")
    lines.append("- Line-item drilldown: use `dim_pay_item.item_desc_canonical`, `standard_code`, `standard_cat`.")
    lines.append("- Optional 3-low: `fact_project_pay_item_metrics.avg_unit_price_3low` (metrics flag required).")

    (doc_dir / "data_dictionary_analysis_schema.md").write_text("\n".join(lines) + "\n")


def write_extraction_rules(doc_dir: Path):
    text = """# Extraction Rules

## Header Parsing Heuristics
- Detect table header row by finding row containing `Item No.` plus at least two `Unit Price` and `Total Price` labels.
- If multiple candidates exist, choose row with strongest match for `Item Description`, `Estimated Quantity`, and `Units`.
- Parse freeform header block above table for:
  - `EAN` using regex `EAN\\s+([A-Za-z0-9-]+)`
  - `Solicitation No.` using regex `Solicitation\\s+No\\.\\s*(.+)`
  - first parseable date-like token as letting date.

## Bidder Block Detection (Merged Cells)
- On table header row, collect all `Unit Price` and `Total Price` columns.
- Pair columns in sequence.
- For each pair, scan up to 10 rows above for bidder name.
- If both columns belong to a merged range, use the merged range top-left value.
- If unmerged, accept identical values across the pair or non-blank value where the other is blank.

## Totals Row Detection
- A row is marked totals when `Item Description` contains `Total Amount` or the phrase `Basis of Bid` (sheet text, case-insensitive).
- Emit totals rows at bidder grain with `schedule_total` from bidder `Total Price` cell.

## Regexes
- Item code:
  - `\\((?:Item)\\s+([A-Za-z]-?\\d+(?:\\.\\d+)?)\\)`
  - `Item\\s+([A-Za-z]-?\\d+(?:\\.\\d+)?)`
- Section code:
  - `\\((?:Section)\\s+([0-9]{4,6})\\)`
"""
    (doc_dir / "extraction_rules.md").write_text(text)


def main():
    parser = argparse.ArgumentParser(description="Generate docs from authoritative schema definitions.")
    parser.add_argument("--docs_dir", default="./docs")
    args = parser.parse_args()

    doc_dir = Path(args.docs_dir)
    doc_dir.mkdir(parents=True, exist_ok=True)

    write_data_model(doc_dir)
    write_compiled_dictionary(doc_dir)
    write_analysis_dictionary(doc_dir)
    write_extraction_rules(doc_dir)


if __name__ == "__main__":
    main()
