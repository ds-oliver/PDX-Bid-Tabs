# Extraction Rules

## Header Parsing Heuristics
- Detect table header row by finding row containing `Item No.` plus at least two `Unit Price` and `Total Price` labels.
- If multiple candidates exist, choose row with strongest match for `Item Description`, `Estimated Quantity`, and `Units`.
- Parse freeform header block above table for:
  - `EAN` using regex `EAN\s+([A-Za-z0-9-]+)`
  - `Solicitation No.` using regex `Solicitation\s+No\.\s*(.+)`
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
  - `\((?:Item)\s+([A-Za-z]-?\d+(?:\.\d+)?)\)`
  - `Item\s+([A-Za-z]-?\d+(?:\.\d+)?)`
- Section code:
  - `\((?:Section)\s+([0-9]{4,6})\)`
