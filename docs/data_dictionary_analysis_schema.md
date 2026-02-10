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
| location_name_raw | str | True | Raw location. | compiled location_name_raw |
| location_code | str | True | Normalized location code. | config/location_dictionary.csv |
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
| pay_item_id | int | False | Surrogate key. | keys.py |
| item_code_raw | str | True | Raw item code. | compiled item_code_raw |
| item_code_norm | str | True | Normalized item code. | compiled item_code_norm |
| section_code_raw | str | True | Raw section code. | compiled section_code_raw |
| section_code_norm | str | True | Normalized section code. | compiled section_code_norm |
| item_desc_canonical | str | False | Canonical item description. | compiled item_description_clean |

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
| schedule_total | float | True | Bidder schedule total. | compiled schedule_total |
| total_row_label | str | True | Totals label text. | compiled totals_row_label |

## Optional Tables (default off)
- Enable `dim_specification` and `bridge_pay_item_spec` with `--emit_spec_tables`.
- Enable `fact_project_pay_item_metrics` with `--emit_metrics`.
- Enable placeholder `fact_award` with `--emit_award_table`.

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
| apparent_low_total_derived | float | True | Derived lowest contractor schedule total. | derived from fact_bid_schedule_total |
| apparent_low_bidder_id_derived | int | True | Derived bidder with lowest contractor schedule total. | derived from fact_bid_schedule_total |
| selection_quality_flag | str | True | Quality of derived low-total selection. | OK|TOTALS_MISMATCH|MISSING_TOTALS|TIE|OTHER |

### fact_award
| Column | Type | Nullable | Definition | Extraction Rule |
|---|---|---|---|---|
| project_id | int | False | Project FK. | dim_project |
| bid_schedule_id | int | False | Schedule FK. | dim_bid_schedule |
| external_selected_bidder_id | int | True | Externally provided selected bidder FK. | optional external source |
| external_selected_amount | float | True | Externally provided selected amount. | optional external source |
| selection_source_note | str | True | External selection source note. | optional external source |

## Example Join
```sql
SELECT p.project_name, s.schedule_name, b.bidder_name_canonical, i.item_desc_canonical, f.total_price
FROM fact_bid_item_price f
JOIN dim_project p ON p.project_id = f.project_id
JOIN dim_bid_schedule s ON s.bid_schedule_id = f.bid_schedule_id
JOIN dim_bidder b ON b.bidder_id = f.bidder_id
JOIN dim_pay_item i ON i.pay_item_id = f.pay_item_id;
```
