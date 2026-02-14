# Data Dictionary: Analysis Schema

Derived convenience tables built from `compiled_excel_itemized_clean.csv`.

## Required Tables (default)
### dim_project
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| project_id | int | False | Surrogate key. | keys.py |
| ean | str | True | Project EAN. | compiled project_ean |
| solicitation_no | str | True | Solicitation number. | compiled solicitation_no |
| project_name | str | True | Project name. | compiled project_name_raw |
| letting_date | str | True | Letting date. | compiled letting_date |
| location_name_raw | str | True | Normalized location token. | compiled location_name_raw |
| location_code | str | True | Mapped location code (PDX,HIO,TTD,TRIP,GVBP,T2,T4,T5,T6,NAVD,SI). | config/location_dictionary.csv |
| source_file | str | False | Workbook file. | compiled source_file |
| source_system | str | False | Source system constant. | excel_bidtab |

### dim_bid_schedule
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| bid_schedule_id | int | False | Surrogate key. | keys.py |
| schedule_name | str | False | Schedule name. | compiled bid_schedule_name |
| schedule_type | str | False | BASE/ALTERNATE. | compiled bid_schedule_type |
| schedule_code | str | True | Alternate code. | compiled bid_schedule_code |

### dim_bidder
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| bidder_id | int | False | Surrogate key. | keys.py |
| bidder_type | str | False | Bidder type. | compiled bidder_type |
| bidder_name_raw | str | False | Raw bidder name. | compiled bidder_name_raw |
| bidder_name_canonical | str | False | Canonical bidder. | compiled bidder_name_canonical |
| contractor_name_canonical | str | True | Canonical contractor label for contractor rows. | derived from bidder_name_canonical |

### dim_pay_item
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| pay_item_id | int | False | Compact surrogate key generated per current extract for joins (not enterprise master id). | sequential by sorted spec_extract + item_desc_canonical |
| spec_extract | str | True | Code-only extraction from item description (e.g., P-620, 012210). | parsed from description token |
| standard_code | str | True | Backward-compatible alias of spec_extract. | derived from parsed description token |
| standard_cat | str | True | Standard category derived from spec_extract. | FAA|PDX|UNKNOWN |
| item_code_raw | str | True | Raw item code. | compiled item_code_raw |
| section_code_raw | str | True | Raw section code. | compiled section_code_raw |
| alt_code | str | True | Secondary code token from description (e.g., second section). | regex from item_description_raw |
| item_desc_raw | str | True | Raw item description from sheet. | compiled item_description_raw |
| item_desc_canonical | str | False | Cleaned description with code fragment removed where parseable. | compiled item_description_clean normalization |

### dim_unit
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| unit_code | str | False | Normalized unit code. | compiled unit_code_norm |
| unit_group | str | True | Unit grouping label. | configurable map |

### fact_bid_item_price
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| project_id | int | False | Project FK. | dim_project |
| bid_schedule_id | int | False | Schedule FK. | dim_bid_schedule |
| pay_item_id | int | False | Pay item FK. | dim_pay_item |
| bidder_id | int | False | Bidder FK. | dim_bidder |
| line_no | str | False | Line number. | compiled line_no |
| quantity | float | True | Estimated quantity. | compiled quantity |
| unit_code | str | True | Unit FK. | compiled unit_code_norm |
| unit_price | float | True | Unit price. | compiled unit_price |
| total_price | float | True | Total price. | compiled total_price |
| total_price_calc | float | True | Calculated total. | compiled total_price_calc |
| source_sheet | str | False | Source sheet. | compiled source_sheet |
| row_index | int | False | Source row index. | compiled source_row_index |
| parse_confidence | float | False | Parse confidence. | compiled parse_confidence |

### fact_bid_schedule_total
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| project_id | int | False | Project FK. | dim_project |
| bid_schedule_id | int | False | Schedule FK. | dim_bid_schedule |
| bidder_id | int | False | Bidder FK. | dim_bidder |
| schedule_total | float | True | Bid total from sheet totals row. | compiled schedule_total |
| total_row_label | str | True | Totals label text. | compiled totals_row_label |

## Optional Tables (default off)
- Enable `dim_specification` and `bridge_pay_item_spec` with `--emit_spec_tables`.
- Enable `fact_project_pay_item_metrics` with `--emit_metrics`.

### dim_specification
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| spec_id | int | False | Surrogate key. | keys.py or spec mapping |
| spec_section_code | str | False | Spec section code. | config/spec_mapping.csv |
| spec_section_name | str | False | Spec section name. | config/spec_mapping.csv |
| spec_division_code | str | True | Spec division code. | config/spec_mapping.csv |
| spec_division_name | str | True | Spec division name. | config/spec_mapping.csv |

### bridge_pay_item_spec
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| pay_item_id | int | False | Pay item FK. | dim_pay_item |
| spec_id | int | False | Specification FK. | dim_specification |
| mapping_method | str | False | Mapping method. | rules |
| confidence | float | False | Mapping confidence. | rules |
| is_curated | bool | False | Curated mapping flag. | optional user-maintained mapping |
| curated_by | str | True | Curator name. | optional user-maintained mapping |
| curated_on | str | True | Curation date. | optional user-maintained mapping |

### fact_project_pay_item_metrics
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| project_id | int | False | Project FK. | dim_project |
| bid_schedule_id | int | False | Schedule FK. | dim_bid_schedule |
| pay_item_id | int | False | Pay item FK. | dim_pay_item |
| avg_unit_price_3low | float | True | Average of three lowest contractor unit prices. | metric calc |
| median_unit_price | float | True | Median contractor unit price. | metric calc |
| min_unit_price | float | True | Minimum contractor unit price. | metric calc |
| num_bidders_valid | int | True | Count of contractors with valid unit price. | metric calc |

## Example Join
```sql
SELECT p.project_name, s.schedule_name, b.bidder_name_canonical, i.item_desc_canonical, f.total_price
FROM fact_bid_item_price f
JOIN dim_project p ON p.project_id = f.project_id
JOIN dim_bid_schedule s ON s.bid_schedule_id = f.bid_schedule_id
JOIN dim_bidder b ON b.bidder_id = f.bidder_id
JOIN dim_pay_item i ON i.pay_item_id = f.pay_item_id;
```

## Dashboard Measure Guidance (ODOT-Style)
- Bidder total comparison: `fact_bid_schedule_total.schedule_total` by `dim_bidder` (exclude engineer estimate).
- Unit price comparison: `fact_bid_item_price.unit_price` by `dim_bidder` and `dim_pay_item`.
- Total price comparison: `fact_bid_item_price.total_price` by `dim_bidder` and `dim_pay_item`.
- Line-item drilldown: use `dim_pay_item.item_desc_canonical`, `standard_code`, `standard_cat`.
- Optional 3-low: `fact_project_pay_item_metrics.avg_unit_price_3low` (metrics flag required).
