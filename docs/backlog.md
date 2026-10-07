# Backlog: candidate fixes for the Port

These are behaviors in the 2026-05-28 baseline that may be defects. The refactor (Phases 1 and 2)
reproduces each one unchanged. Hogan raises them with the Port; none is fixed without a Port
decision.

| # | Item | Baseline behavior | Where | Risk |
|---|---|---|---|---|
| B-01 | Blank `spec_type` in the crosswalk | Passes. The allowed-values check runs on `dropna()`, so a null never fails | `03_load_crosswalk.py`, hard-fail QA cell | A mapped item lands in the mart with no spec type; Power BI spec filters miss it |
| B-02 | Blank `catalog_division` | Silently filled with `99 Uncategorized / Not Listed` | `03_load_crosswalk.py`, defensive cleanups | Staff do not learn the row is incomplete; Run Health counts it but does not halt |
| B-03 | Blank `catalog_cost_code` | Not checked | `03_load_crosswalk.py` | Mart rows with no cost code; `faa_item_code` and `port_section_code` both null |
| B-04 | `SKIP_FILES` is hard-coded | `["PDX_2017D013.xlsx"]` in notebook code, not config | `01_parse_single_bidtab.py`, config cell | Excluding another file needs a code change, not a config edit (NFR-01) |
