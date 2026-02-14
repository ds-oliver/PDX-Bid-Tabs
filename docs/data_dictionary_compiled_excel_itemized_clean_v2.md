# Data Dictionary: compiled_excel_itemized_clean.csv (v2)

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

| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| schema_version | str | False | Schema version constant. | constant 2.0 |
| extract_run_id | str | False | Unique ETL run id. | CLI arg --run_id |
| source_file | str | False | Source workbook filename. | input file name |
| source_sheet | str | False | Source worksheet name. | worksheet title |
| source_row_index | int | False | Excel row index for extracted row. | parsed data row |
| source_table_header_row | int | False | Detected table header row index. | header detection |
| project_ean | str | True | Project EAN parsed from header. | regex EAN |
| solicitation_no | str | True | Solicitation identifier. | regex Solicitation No. |
| letting_date_raw | str | True | Unparsed letting date token. | header scan |
| letting_date | str | True | Normalized letting date (YYYY-MM-DD). | date parsing |
| location_name_raw | str | True | Normalized location token from header (alphanumeric uppercase). | header heuristic |
| project_name_raw | str | True | Project title text from header. | header heuristic |
| bid_schedule_name | str | False | Bid schedule name (sheet title). | worksheet title |
| bid_schedule_type | str | False | Schedule type BASE or ALTERNATE. | sheet title heuristic |
| bid_schedule_code | str | True | Schedule code such as ALT_1. | sheet title regex |
| line_no | str | True | Line item number preserving leading zeros. | Item No. column |
| item_description_raw | str | False | Raw item description. | Item Description column |
| item_description_clean | str | False | Normalized description text. | clean_whitespace |
| item_code_raw | str | True | Raw pay item code from description. | regex extraction |
| item_code_norm | str | True | Normalized pay item code. | uppercase/no spaces |
| section_code_raw | str | True | Raw section code from description. | regex extraction |
| section_code_norm | str | True | Normalized section code digits. | digits only |
| quantity | float | True | Estimated quantity. | Estimated Quantity column |
| unit_code_raw | str | True | Raw unit code. | Units column |
| unit_code_norm | str | True | Normalized unit code uppercase. | normalize unit |
| bidder_name_raw | str | False | Raw bidder label above Unit/Total columns. | bidder block parsing |
| bidder_name_canonical | str | False | Canonical bidder name. | name normalization |
| bidder_type | str | False | CONTRACTOR or ENGINEERS_ESTIMATE. | bidder classifier |
| is_engineers_estimate | bool | False | Whether row is engineer estimate. | bidder classifier |
| unit_price | float | True | Bidder unit price. | Unit Price column |
| total_price | float | True | Bidder total line price. | Total Price column |
| total_price_calc | float | True | Calculated unit_price * quantity. | QA arithmetic |
| price_valid_flag | bool | False | Price arithmetic validity. | QA arithmetic + bidder rule |
| parse_confidence | float | False | Parse confidence 0-1. | parsing confidence heuristic |
| is_totals_row | bool | False | Whether row is totals/basis row. | totals detection |
| totals_row_label | str | True | Totals row description label. | Item Description column |
| schedule_total | float | True | Bidder schedule total from totals row. | Total Price cell on totals row |
