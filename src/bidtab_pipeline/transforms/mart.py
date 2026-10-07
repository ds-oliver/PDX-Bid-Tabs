"""mart_bid_analysis build: port of reference notebook 04's mart, view, and checks.

The SQL is unchanged from 04; only table names come from Settings
(tests/unit/test_sql_ports.py compares the runtime SQL for both
INCLUDE_ENG_EST values). The mart contract is frozen (FR-40).
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession

from bidtab_pipeline.settings import Settings

SILVER_TABLE_NAME = "silver_bid_items"
CROSSWALK_TABLE_NAME = "int_crosswalk"
MART_TABLE_NAME = "mart_bid_analysis"
UNMAPPED_VIEW_NAME = "crosswalk_unmapped_items"


def build_mart(spark: SparkSession, settings: Settings, INCLUDE_ENG_EST: bool) -> None:  # noqa: N803 - name kept from 04
    """Rebuild mart_bid_analysis from Silver and the crosswalk.

    INCLUDE_ENG_EST=False (the default in notebook 04) keeps only contractor
    bids; True keeps Engineer's Estimate rows too. Bronze and Silver always keep them.
    """
    SILVER_TABLE = settings.table(SILVER_TABLE_NAME)
    CROSSWALK_TABLE = settings.table(CROSSWALK_TABLE_NAME)
    MART_TABLE = settings.table(MART_TABLE_NAME)

    # Build the EE filter clause based on the toggle.
    # When False (default): exclude EE rows from the mart. Power BI sees only contractor bids.
    # When True: keep EE rows. Downstream visuals should filter on is_engineers_estimate as needed.
    ee_filter_clause = "" if INCLUDE_ENG_EST else "WHERE NOT s.is_engineers_estimate"

    spark.sql(
        f"""
        CREATE OR REPLACE TABLE {MART_TABLE} AS
        SELECT
          SHA2(CONCAT_WS('~', s.bid_type, s.ean, s.item_no, s.awarded_bidder_canonical), 256) AS bid_item_sk,
          CONCAT_WS('~', s.bid_type, s.ean, s.item_no) AS natural_key,

          s.ean, s.project_name_full, s.project_name, s.airport_name,
          s.solicitation_no, s.bid_date, s.bid_year,

          s.source_file, s.bid_type, s.tab_type,

          s.item_no, s.item_no_sort,

          -- Three-layer description hierarchy:
          --   raw         = verbatim from the bid tab
          --   normalized  = silver's lightly-cleaned version (spacing, capitalization, punctuation)
          --   standardized = Jennifer Scott's deeply-standardized name from the catalog crosswalk
          s.item_description_raw,
          s.item_description_normalized,

          CASE
            WHEN c.raw_join_key IS NULL
              THEN '⚠️ Unmapped — see crosswalk_unmapped_items'
            ELSE c.item_description_normalized
          END AS item_description_standardized,

          -- Legacy alias of item_description_standardized for BI dashboard compatibility.
          -- Kim's existing Power BI measures reference this name.
          CASE
            WHEN c.raw_join_key IS NULL
              THEN '⚠️ Unmapped — see crosswalk_unmapped_items'
            ELSE c.item_description_normalized
          END AS catalog_item_description,

          s.estimated_quantity,
          s.unit_clean AS unit,

          -- Catalog mapping fields from Jennifer Scott's Final Recommended Line Item List.
          -- Unmapped rows (LEFT JOIN miss) get '100 - Unmapped' / 'UNMAPPED' fallback labels
          -- so dashboards stay navigable. See crosswalk_unmapped_items view for resolution list.
          CASE
            WHEN c.raw_join_key IS NULL THEN '100 - Unmapped'
            ELSE c.catalog_division
          END AS catalog_division,

          CASE
            WHEN c.raw_join_key IS NULL THEN 'UNMAPPED'
            ELSE c.catalog_cost_code
          END AS catalog_cost_code,

          c.catalog_cost_code_desc,
          c.catalog_cost_code_original,

          CASE
            WHEN c.raw_join_key IS NULL THEN 'UNMAPPED'
            ELSE c.spec_type
          END AS spec_type,

          -- Deprecated field (no source data in current crosswalk). Retained as NULL
          -- column for backward compatibility with existing BI references.
          CAST(NULL AS STRING) AS crosswalk_confidence,

          c.faa_item_code,
          c.port_section_code,

          CASE
            WHEN c.raw_join_key IS NOT NULL THEN TRUE
            ELSE FALSE
          END AS is_catalog_mapped,

          s.awarded_bidder_canonical AS contractor_name_canonical,
          s.contractor_position,
          s.is_engineers_estimate,
          s.is_awarded_bid,

          s.unit_price, s.total_price,

          CASE
            WHEN s.estimated_quantity IS NOT NULL
                 AND s.estimated_quantity > 0
                 AND s.total_price IS NOT NULL
              THEN ROUND(s.total_price / s.estimated_quantity, 2)
            ELSE NULL
          END AS effective_unit_price,

          s.unit_price_null_flag, s.total_price_zero_flag, s.price_suspicious_flag,

          s.bronze_loaded_at,
          s.silver_loaded_at,
          current_timestamp() AS mart_loaded_at

        FROM {SILVER_TABLE} s
        LEFT JOIN {CROSSWALK_TABLE} c
          ON LOWER(TRIM(s.item_description_raw)) = c.raw_join_key
        {ee_filter_clause}
        """
    )
    print(f"Mart table {MART_TABLE} built successfully.")
    print(f"  INCLUDE_ENG_EST = {INCLUDE_ENG_EST}")
    print(f"  Engineer's Estimate rows {'INCLUDED' if INCLUDE_ENG_EST else 'EXCLUDED'} from this mart build.")


def ee_toggle_check(spark: SparkSession, settings: Settings, INCLUDE_ENG_EST: bool) -> DataFrame:  # noqa: N803
    """Verify the INCLUDE_ENG_EST toggle behavior."""
    MART_TABLE = settings.table(MART_TABLE_NAME)
    ee_check = spark.sql(f"""
        SELECT
          COUNT(*) AS total_mart_rows,
          SUM(CASE WHEN is_engineers_estimate THEN 1 ELSE 0 END) AS ee_rows,
          SUM(CASE WHEN NOT is_engineers_estimate THEN 1 ELSE 0 END) AS contractor_rows,
          CASE
            WHEN {str(INCLUDE_ENG_EST).lower()}
                 AND SUM(CASE WHEN is_engineers_estimate THEN 1 ELSE 0 END) = 0
              THEN '⚠️ INCLUDE_ENG_EST=True but no EE rows present — check Bronze/Silver'
            WHEN NOT {str(INCLUDE_ENG_EST).lower()}
                 AND SUM(CASE WHEN is_engineers_estimate THEN 1 ELSE 0 END) > 0
              THEN '⚠️ INCLUDE_ENG_EST=False but EE rows present — filter failed'
            ELSE '✅ EE toggle behavior matches expectation'
          END AS status
        FROM {MART_TABLE}
    """)
    return ee_check


def build_unmapped_view(spark: SparkSession, settings: Settings) -> None:
    """crosswalk_unmapped_items: raw descriptions with no crosswalk row, for staff to resolve."""
    MART_TABLE = settings.table(MART_TABLE_NAME)
    UNMAPPED_VIEW = settings.table(UNMAPPED_VIEW_NAME)

    spark.sql(
        f"""
        CREATE OR REPLACE VIEW {UNMAPPED_VIEW} AS
        SELECT
          item_description_raw,
          COUNT(*) AS affected_row_count,
          COUNT(DISTINCT ean) AS affected_project_count,
          COLLECT_SET(ean) AS example_projects,
          MAX(bid_year) AS latest_bid_year,
          MAX(bid_date) AS latest_bid_date,
          'Add row to Final_Recommended_Line_Item_List.csv with: item_description_raw, item_description_normalized, catalog_cost_code_original, catalog_cost_code, spec_type, catalog_division, catalog_cost_code_desc. Re-upload to /Volumes/pop-poc/bidtab/config/ then rerun notebooks 03 and 04.' AS suggested_action,
          current_timestamp() AS report_generated_at
        FROM {MART_TABLE}
        WHERE NOT is_catalog_mapped
        GROUP BY item_description_raw
        ORDER BY affected_row_count DESC, affected_project_count DESC
        """
    )
    print(f"Unmapped resolution view {UNMAPPED_VIEW} built successfully.")


# Unchanged from 04, in display order. Placeholders: {MART_TABLE}, {SILVER_TABLE}, {UNMAPPED_VIEW}.
MART_CHECKS = [
    """
        SELECT
          item_description_raw,
          affected_row_count,
          affected_project_count,
          example_projects,
          latest_bid_year,
          latest_bid_date
        FROM {UNMAPPED_VIEW}
        """,
    """
        SELECT
          'mart_vs_silver' AS check_name,
          s.silver_rows,
          m.mart_rows,
          CASE WHEN s.silver_rows = m.mart_rows THEN 'PASS' ELSE 'FAIL' END AS status
        FROM
          (SELECT COUNT(*) AS silver_rows FROM {SILVER_TABLE}) s,
          (SELECT COUNT(*) AS mart_rows FROM {MART_TABLE}) m
        """,
    """
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) AS catalog_mapped_rows,

          -- Unmapped: raw description not found in Jennifer's file at all
          SUM(CASE WHEN NOT is_catalog_mapped THEN 1 ELSE 0 END) AS unmapped_rows,
          SUM(CASE WHEN catalog_division = '100 - Unmapped' THEN 1 ELSE 0 END) AS unmapped_division_rows,

          -- Uncategorized: in Jennifer's file but Division was left blank
          SUM(CASE WHEN catalog_division = '99 Uncategorized / Not Listed' THEN 1 ELSE 0 END) AS uncategorized_division_rows,
          SUM(CASE WHEN spec_type = 'UNK' THEN 1 ELSE 0 END) AS unk_spec_type_rows,

          ROUND(SUM(CASE WHEN is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS mapped_pct,

          -- Three-layer description cardinality (raw → cleaned → standardized)
          COUNT(DISTINCT item_description_raw) AS distinct_raw,
          COUNT(DISTINCT item_description_normalized) AS distinct_normalized,
          COUNT(DISTINCT item_description_standardized) AS distinct_standardized,

          COUNT(DISTINCT catalog_division) AS distinct_divisions,
          COUNT(DISTINCT catalog_cost_code) AS distinct_sections,
          COUNT(DISTINCT catalog_cost_code_desc) AS distinct_section_descs
        FROM {MART_TABLE}
        """,
    """
        SELECT
          ean,
          project_name_full,
          bid_year,
          COUNT(DISTINCT contractor_name_canonical) AS total_bidders,
          MAX(CASE WHEN is_awarded_bid THEN contractor_name_canonical END) AS awarded_contractor,
          SUM(CASE WHEN is_awarded_bid THEN total_price ELSE 0 END) AS awarded_total_value,
          COUNT(DISTINCT item_no) AS item_count
        FROM {MART_TABLE}
        WHERE tab_type = 'BASE'
        GROUP BY ean, project_name_full, bid_year
        ORDER BY bid_year, ean
        """,
    """
        SELECT
          item_description_standardized,
          catalog_division,
          catalog_cost_code,
          catalog_cost_code_desc,
          spec_type,
          COUNT(*) AS row_count,
          COUNT(DISTINCT ean) AS project_count,
          ROUND(AVG(unit_price), 2) AS avg_unit_price,
          ROUND(MIN(unit_price), 2) AS min_unit_price,
          ROUND(MAX(unit_price), 2) AS max_unit_price,
          ROUND(AVG(total_price), 2) AS avg_total_price
        FROM {MART_TABLE}
        WHERE is_catalog_mapped
          AND unit_price IS NOT NULL
          AND unit_price > 0
        GROUP BY item_description_standardized, catalog_division, catalog_cost_code, catalog_cost_code_desc, spec_type
        ORDER BY project_count DESC, row_count DESC
        LIMIT 25
        """,
    """
        SELECT
          bid_year,
          item_description_standardized,
          COUNT(DISTINCT ean) AS projects,
          ROUND(AVG(unit_price), 2) AS avg_unit_price,
          ROUND(AVG(total_price), 2) AS avg_total_price,
          ROUND(AVG(CASE WHEN is_awarded_bid THEN total_price END), 2) AS avg_awarded_price
        FROM {MART_TABLE}
        WHERE item_description_standardized LIKE '%Mobilization%'
          AND tab_type = 'BASE'
          AND total_price IS NOT NULL
          AND total_price > 0
        GROUP BY bid_year, item_description_standardized
        ORDER BY bid_year, item_description_standardized
        """,
    """
        SELECT
          COUNT(*) AS total_rows,
          SUM(CASE WHEN unit_price_null_flag THEN 1 ELSE 0 END) AS null_unit_price,
          SUM(CASE WHEN total_price_zero_flag THEN 1 ELSE 0 END) AS zero_total_price,
          SUM(CASE WHEN price_suspicious_flag THEN 1 ELSE 0 END) AS suspicious_price,
          SUM(CASE WHEN NOT is_catalog_mapped THEN 1 ELSE 0 END) AS not_catalog_mapped,
          ROUND(SUM(CASE WHEN unit_price IS NOT NULL AND unit_price > 0 AND is_catalog_mapped THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS clean_and_mapped_pct
        FROM {MART_TABLE}
        """,
    """
        SELECT *
        FROM {MART_TABLE}
        WHERE is_catalog_mapped
          AND is_awarded_bid
        ORDER BY ean, item_no_sort
        LIMIT 30
        """,
    """
        SELECT
          item_description_raw,
          COUNT(*) AS row_count,
          COUNT(DISTINCT ean) AS project_count,
          COLLECT_SET(catalog_division) AS catalog_divisions,
          COLLECT_SET(spec_type) AS spec_types
        FROM {MART_TABLE}
        WHERE NOT is_catalog_mapped
        GROUP BY item_description_raw
        ORDER BY row_count DESC
        """,
    """-- 1. spec_type fan-out at mart grain
SELECT spec_type, COUNT(*) AS row_count, COUNT(DISTINCT ean) AS projects
FROM {MART_TABLE}
GROUP BY spec_type ORDER BY spec_type;
""",
    """-- 2. Airport normalization (Silver)
SELECT airport_name, COUNT(DISTINCT ean) AS projects, COUNT(*) AS rows
FROM {SILVER_TABLE}
GROUP BY airport_name ORDER BY airport_name;
""",
    """
-- 3. Hyphenated item_no audit
SELECT source_file, COUNT(*) AS total, SUM(CASE WHEN item_no_sort IS NULL THEN 1 ELSE 0 END) AS null_sort
FROM {SILVER_TABLE}
GROUP BY source_file HAVING null_sort > 0;
""",
    """SELECT DISTINCT item_no, item_no_sort
FROM {SILVER_TABLE}
WHERE source_file = 'PDX_2021D007 Bid Tab.xlsx'
ORDER BY item_no;""",
    """-- 4. effective_unit_price sanity — 15 null unit prices should have backfill
SELECT
  SUM(CASE WHEN unit_price_null_flag THEN 1 ELSE 0 END) AS null_unit_price_rows,
  SUM(CASE WHEN unit_price_null_flag AND effective_unit_price IS NOT NULL THEN 1 ELSE 0 END) AS backfilled,
  SUM(CASE WHEN unit_price_null_flag AND effective_unit_price IS NULL THEN 1 ELSE 0 END) AS still_null
FROM {MART_TABLE};""",
]


def mart_checks(spark: SparkSession, settings: Settings) -> list[DataFrame]:
    """The checks 04 displays between the unmapped view and the Run Health Summary, in order."""
    names = {
        "MART_TABLE": settings.table(MART_TABLE_NAME),
        "SILVER_TABLE": settings.table(SILVER_TABLE_NAME),
        "UNMAPPED_VIEW": settings.table(UNMAPPED_VIEW_NAME),
    }
    return [spark.sql(q.format(**names)) for q in MART_CHECKS]
