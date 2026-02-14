from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

SCHEMA_VERSION = "2.0"
SOURCE_SYSTEM = "excel_bidtab"


@dataclass(frozen=True)
class ColumnDef:
    name: str
    dtype: str
    nullable: bool
    description: str
    source_rule: str


COMPILED_COLUMNS: List[ColumnDef] = [
    ColumnDef("schema_version", "str", False, "Schema version constant.", "constant 2.0"),
    ColumnDef("extract_run_id", "str", False, "Unique ETL run id.", "CLI arg --run_id"),
    ColumnDef("source_file", "str", False, "Source workbook filename.", "input file name"),
    ColumnDef("source_sheet", "str", False, "Source worksheet name.", "worksheet title"),
    ColumnDef("source_row_index", "int", False, "Excel row index for extracted row.", "parsed data row"),
    ColumnDef("source_table_header_row", "int", False, "Detected table header row index.", "header detection"),
    ColumnDef("project_ean", "str", True, "Project EAN parsed from header.", "regex EAN"),
    ColumnDef("solicitation_no", "str", True, "Solicitation identifier.", "regex Solicitation No."),
    ColumnDef("letting_date_raw", "str", True, "Unparsed letting date token.", "header scan"),
    ColumnDef("letting_date", "str", True, "Normalized letting date (YYYY-MM-DD).", "date parsing"),
    ColumnDef("location_name_raw", "str", True, "Normalized location token from header (alphanumeric uppercase).", "header heuristic"),
    ColumnDef("project_name_raw", "str", True, "Project title text from header.", "header heuristic"),
    ColumnDef("bid_schedule_name", "str", False, "Bid schedule name (sheet title).", "worksheet title"),
    ColumnDef("bid_schedule_type", "str", False, "Schedule type BASE or ALTERNATE.", "sheet title heuristic"),
    ColumnDef("bid_schedule_code", "str", True, "Schedule code such as ALT_1.", "sheet title regex"),
    ColumnDef("line_no", "str", True, "Line item number preserving leading zeros.", "Item No. column"),
    ColumnDef("item_description_raw", "str", False, "Raw item description.", "Item Description column"),
    ColumnDef("item_description_clean", "str", False, "Normalized description text.", "clean_whitespace"),
    ColumnDef("item_code_raw", "str", True, "Raw pay item code from description.", "regex extraction"),
    ColumnDef("item_code_norm", "str", True, "Normalized pay item code.", "uppercase/no spaces"),
    ColumnDef("section_code_raw", "str", True, "Raw section code from description.", "regex extraction"),
    ColumnDef("section_code_norm", "str", True, "Normalized section code digits.", "digits only"),
    ColumnDef("quantity", "float", True, "Estimated quantity.", "Estimated Quantity column"),
    ColumnDef("unit_code_raw", "str", True, "Raw unit code.", "Units column"),
    ColumnDef("unit_code_norm", "str", True, "Normalized unit code uppercase.", "normalize unit"),
    ColumnDef("bidder_name_raw", "str", False, "Raw bidder label above Unit/Total columns.", "bidder block parsing"),
    ColumnDef("bidder_name_canonical", "str", False, "Canonical bidder name.", "name normalization"),
    ColumnDef("bidder_type", "str", False, "CONTRACTOR or ENGINEERS_ESTIMATE.", "bidder classifier"),
    ColumnDef("is_engineers_estimate", "bool", False, "Whether row is engineer estimate.", "bidder classifier"),
    ColumnDef("unit_price", "float", True, "Bidder unit price.", "Unit Price column"),
    ColumnDef("total_price", "float", True, "Bidder total line price.", "Total Price column"),
    ColumnDef("total_price_calc", "float", True, "Calculated unit_price * quantity.", "QA arithmetic"),
    ColumnDef("price_valid_flag", "bool", False, "Price arithmetic validity.", "QA arithmetic + bidder rule"),
    ColumnDef("parse_confidence", "float", False, "Parse confidence 0-1.", "parsing confidence heuristic"),
    ColumnDef("is_totals_row", "bool", False, "Whether row is totals/basis row.", "totals detection"),
    ColumnDef("totals_row_label", "str", True, "Totals row description label.", "Item Description column"),
    ColumnDef("schedule_total", "float", True, "Bidder schedule total from totals row.", "Total Price cell on totals row"),
]

COMPILED_COLUMN_ORDER = [c.name for c in COMPILED_COLUMNS]

STAR_SCHEMAS: Dict[str, List[ColumnDef]] = {
    "dim_project": [
        ColumnDef("project_id", "int", False, "Surrogate key.", "keys.py"),
        ColumnDef("ean", "str", True, "Project EAN.", "compiled project_ean"),
        ColumnDef("solicitation_no", "str", True, "Solicitation number.", "compiled solicitation_no"),
        ColumnDef("project_name", "str", True, "Project name.", "compiled project_name_raw"),
        ColumnDef("letting_date", "str", True, "Letting date.", "compiled letting_date"),
        ColumnDef("location_name_raw", "str", True, "Normalized location token.", "compiled location_name_raw"),
        ColumnDef("location_code", "str", True, "Mapped location code (PDX,HIO,TTD,TRIP,GVBP,T2,T4,T5,T6,NAVD,SI).", "config/location_dictionary.csv"),
        ColumnDef("source_file", "str", False, "Workbook file.", "compiled source_file"),
        ColumnDef("source_system", "str", False, "Source system constant.", "excel_bidtab"),
    ],
    "dim_bid_schedule": [
        ColumnDef("bid_schedule_id", "int", False, "Surrogate key.", "keys.py"),
        ColumnDef("schedule_name", "str", False, "Schedule name.", "compiled bid_schedule_name"),
        ColumnDef("schedule_type", "str", False, "BASE/ALTERNATE.", "compiled bid_schedule_type"),
        ColumnDef("schedule_code", "str", True, "Alternate code.", "compiled bid_schedule_code"),
    ],
    "dim_bidder": [
        ColumnDef("bidder_id", "int", False, "Surrogate key.", "keys.py"),
        ColumnDef("bidder_type", "str", False, "Bidder type.", "compiled bidder_type"),
        ColumnDef("bidder_name_raw", "str", False, "Raw bidder name.", "compiled bidder_name_raw"),
        ColumnDef("bidder_name_canonical", "str", False, "Canonical bidder.", "compiled bidder_name_canonical"),
        ColumnDef("contractor_name_canonical", "str", True, "Canonical contractor label for contractor rows.", "derived from bidder_name_canonical"),
    ],
    "dim_pay_item": [
        ColumnDef("pay_item_id", "int", False, "Compact surrogate key generated per current extract for joins (not enterprise master id).", "sequential by sorted spec_extract + item_desc_canonical"),
        ColumnDef("spec_extract", "str", True, "Code-only extraction from item description (e.g., P-620, 012210).", "parsed from description token"),
        ColumnDef("standard_code", "str", True, "Backward-compatible alias of spec_extract.", "derived from parsed description token"),
        ColumnDef("standard_cat", "str", True, "Standard category derived from spec_extract.", "FAA|PDX|UNKNOWN"),
        ColumnDef("item_code_raw", "str", True, "Raw item code.", "compiled item_code_raw"),
        ColumnDef("section_code_raw", "str", True, "Raw section code.", "compiled section_code_raw"),
        ColumnDef("alt_code", "str", True, "Secondary code token from description (e.g., second section).", "regex from item_description_raw"),
        ColumnDef("item_desc_raw", "str", True, "Raw item description from sheet.", "compiled item_description_raw"),
        ColumnDef("item_desc_canonical", "str", False, "Cleaned description with code fragment removed where parseable.", "compiled item_description_clean normalization"),
    ],
    "dim_specification": [
        ColumnDef("spec_id", "int", False, "Surrogate key.", "keys.py or spec mapping"),
        ColumnDef("spec_section_code", "str", False, "Spec section code.", "config/spec_mapping.csv"),
        ColumnDef("spec_section_name", "str", False, "Spec section name.", "config/spec_mapping.csv"),
        ColumnDef("spec_division_code", "str", True, "Spec division code.", "config/spec_mapping.csv"),
        ColumnDef("spec_division_name", "str", True, "Spec division name.", "config/spec_mapping.csv"),
    ],
    "dim_unit": [
        ColumnDef("unit_code", "str", False, "Normalized unit code.", "compiled unit_code_norm"),
        ColumnDef("unit_group", "str", True, "Unit grouping label.", "configurable map"),
    ],
    "bridge_pay_item_spec": [
        ColumnDef("pay_item_id", "int", False, "Pay item FK.", "dim_pay_item"),
        ColumnDef("spec_id", "int", False, "Specification FK.", "dim_specification"),
        ColumnDef("mapping_method", "str", False, "Mapping method.", "rules"),
        ColumnDef("confidence", "float", False, "Mapping confidence.", "rules"),
        ColumnDef("is_curated", "bool", False, "Curated mapping flag.", "optional user-maintained mapping"),
        ColumnDef("curated_by", "str", True, "Curator name.", "optional user-maintained mapping"),
        ColumnDef("curated_on", "str", True, "Curation date.", "optional user-maintained mapping"),
    ],
    "fact_bid_item_price": [
        ColumnDef("project_id", "int", False, "Project FK.", "dim_project"),
        ColumnDef("bid_schedule_id", "int", False, "Schedule FK.", "dim_bid_schedule"),
        ColumnDef("pay_item_id", "int", False, "Pay item FK.", "dim_pay_item"),
        ColumnDef("bidder_id", "int", False, "Bidder FK.", "dim_bidder"),
        ColumnDef("line_no", "str", False, "Line number.", "compiled line_no"),
        ColumnDef("quantity", "float", True, "Estimated quantity.", "compiled quantity"),
        ColumnDef("unit_code", "str", True, "Unit FK.", "compiled unit_code_norm"),
        ColumnDef("unit_price", "float", True, "Unit price.", "compiled unit_price"),
        ColumnDef("total_price", "float", True, "Total price.", "compiled total_price"),
        ColumnDef("total_price_calc", "float", True, "Calculated total.", "compiled total_price_calc"),
        ColumnDef("source_sheet", "str", False, "Source sheet.", "compiled source_sheet"),
        ColumnDef("row_index", "int", False, "Source row index.", "compiled source_row_index"),
        ColumnDef("parse_confidence", "float", False, "Parse confidence.", "compiled parse_confidence"),
    ],
    "fact_bid_schedule_total": [
        ColumnDef("project_id", "int", False, "Project FK.", "dim_project"),
        ColumnDef("bid_schedule_id", "int", False, "Schedule FK.", "dim_bid_schedule"),
        ColumnDef("bidder_id", "int", False, "Bidder FK.", "dim_bidder"),
        ColumnDef("schedule_total", "float", True, "Bid total from sheet totals row.", "compiled schedule_total"),
        ColumnDef("total_row_label", "str", True, "Totals label text.", "compiled totals_row_label"),
    ],
    "fact_project_pay_item_metrics": [
        ColumnDef("project_id", "int", False, "Project FK.", "dim_project"),
        ColumnDef("bid_schedule_id", "int", False, "Schedule FK.", "dim_bid_schedule"),
        ColumnDef("pay_item_id", "int", False, "Pay item FK.", "dim_pay_item"),
        ColumnDef("avg_unit_price_3low", "float", True, "Average of three lowest contractor unit prices.", "metric calc"),
        ColumnDef("median_unit_price", "float", True, "Median contractor unit price.", "metric calc"),
        ColumnDef("min_unit_price", "float", True, "Minimum contractor unit price.", "metric calc"),
        ColumnDef("num_bidders_valid", "int", True, "Count of contractors with valid unit price.", "metric calc"),
    ],
}


def empty_for_dtype(dtype: str):
    if dtype in {"float", "int"}:
        return None
    if dtype == "bool":
        return False
    return ""


def coerce_compiled_record(record: dict) -> dict:
    out = {}
    for col in COMPILED_COLUMNS:
        value = record.get(col.name, None)
        if value is None:
            if col.name == "schema_version":
                value = SCHEMA_VERSION
            elif col.name == "price_valid_flag":
                value = False
            elif col.name == "parse_confidence":
                value = 0.0
            elif col.nullable:
                value = empty_for_dtype(col.dtype)
            else:
                value = empty_for_dtype(col.dtype)
        if col.dtype == "str" and value is None:
            value = ""
        out[col.name] = value
    return out


def compiled_columns() -> List[str]:
    return COMPILED_COLUMN_ORDER[:]
