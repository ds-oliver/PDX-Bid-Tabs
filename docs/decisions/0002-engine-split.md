# 0002: Engine split between Spark SQL and plain Python

**Status:** Decided 2026-10-07 (Hogan).

## Decision

- **Spark SQL** stays the engine for Silver (notebook 02), the mart and its checks
  (notebook 04), and every Delta table write.
- **Plain Python** (openpyxl, pandas, pdfplumber) stays the engine for sources
  (workbook parsing, PDF parsing) and config loading. This is where the baseline
  already uses pandas.
- **No rewrite of 02 or 04 in pandas.** A pandas port is a possible later change,
  only after Gate 2b passes and only if Port IT asks for it.

## Reasons

1. **The tables must land in Unity Catalog Delta.** Power BI reads
   `pop-poc.bidtab.mart_bid_analysis` through the `SQL-Serverless-X-Small-PowerBiOnly`
   SQL warehouse. Whatever computes the mart, it is written as a Delta table in
   Unity Catalog, so Spark is already in the path.
2. **Regular expressions differ.** Spark's `regexp_replace` and `RLIKE` use Java
   regex. Python `re` differs in escaping, character classes, and replacement syntax
   (`$1` in Java, `\1` in Python). 02 uses both: Spark SQL for airport names and
   solicitation numbers, Python `re` inside the `normalize_description` UDF.
3. **Null, trim, rounding, and decimal semantics differ.** Examples in the
   baseline: `TRIM` strips spaces only in Spark, all whitespace in Python;
   `NULL = 0` is NULL in SQL (which is why `price_suspicious_flag` can be NULL,
   backlog B-07) but `NaN == 0` is False in pandas; `ROUND` is half-up in Spark
   and half-to-even in Python and numpy; pandas turns integer columns with nulls
   into floats.
4. **The current port is proven equivalent because it reuses the reference SQL
   text unchanged.** `tests/unit/test_sql_ports.py` checks that every statement
   02 and 04 send to Spark matches the reference; the snapshot tests check the
   results. A pandas rewrite would lose that proof and need a new one.

## Consequences

- Local tests need Spark (JDK 17, `pyspark`, `delta-spark`; the `local` extra).
- The PDF source emits the Bronze contract with plain Python, then reuses the
  shared Spark SQL transforms against its isolated tables (BRD Section 11 step 3).
