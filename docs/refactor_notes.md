# Refactor notes: xlsx path (Phases 1 and 2)

**Status 2026-10-07:** Gate 2a passed. Gate 2b blocked on Port inputs.

## Notebook to package map

The job's five notebooks are now thin entry points in `notebooks/`. Names, task
order, tables, config files, and printed output are unchanged.

| Notebook | Package code | Writes |
|---|---|---|
| `01_parse_single_bidtab` | `sources/xlsx/parser.py` (verbatim copy of 01's helpers), `sources/xlsx/bronze.py` | `bronze_raw_rows` |
| `02_build_silver` | `config_loader/silver_config.py`, `transforms/silver.py` | `silver_bid_items`, `ref_awarded_bids` |
| `03_load_crosswalk` | `config_loader/crosswalk.py` (verbatim copy of 03's load and guardrails), `transforms/crosswalk.py` | `int_crosswalk` |
| `04_build_mart` | `transforms/mart.py`, `quality/run_health.py`, `quality/audit_log.py`, `quality/delta_report.py` | `mart_bid_analysis`, `crosswalk_unmapped_items`, `pipeline_run_log`, `pipeline_file_log` |
| `05_export_csvs` | `io/exports.py` | `/Volumes/pop-poc/bidtab/exports/*.csv` |

`INCLUDE_ENG_EST` stays a literal at the top of notebook 04, where analysts flip it.
`settings.py` holds the table prefix and volume root; on Databricks the defaults
are the production values, so the job needs no parameters.

## How equivalence is proven

- `tests/golden/test_refactored_equivalence.py`: the refactored notebooks
  reproduce the reference snapshots exactly in three scenarios (first run;
  second run with a file added and one removed; `INCLUDE_ENG_EST = True`).
- `tests/golden/test_reference_snapshots.py`: the unchanged reference notebooks
  reproduce the same snapshots, and both versions of 03 halt on each crosswalk defect.
- `tests/unit/test_verbatim_ports.py`: copied parser and guardrail code is byte-identical to the reference.
- `tests/unit/test_sql_ports.py`: every SQL statement 02 and 04 send to Spark, and 04's printed output,
  match the reference for both `INCLUDE_ENG_EST` values.

## Gate 2b: production inputs

Put the Port's snapshots here (gitignored):

```
local_inputs/volumes/source_files/   top level of /Volumes/pop-poc/bidtab/source_files/
local_inputs/volumes/config/         /Volumes/pop-poc/bidtab/config/
local_inputs/fresh_run/exports/      the six 05 CSVs from a fresh job run on those inputs
```

Then run `pytest tests/golden/test_production_parity.py -rs`. If the inputs are
the 2026-05-28 inputs, add `BIDTAB_INPUTS_MATCH_GOLDEN=1` to assert the golden
counts; otherwise the differences are listed in the skip message.

## For Port IT (Carrie)

- **Importing the package.** Each notebook adds `../src` to `sys.path`, which
  works when the repo is a Databricks Git folder with `notebooks/` and `src/`
  side by side. If Port IT prefers a wheel in the job environment, the bootstrap
  cell is harmless and can be removed. Decision needed before deployment.
- **Job definition.** `resources/bidtab_job.yml` is not written yet: it needs the
  job JSON. The README notebook says the job has four tasks (01 to 04), but the
  2026-05-28 run includes a 05 export. The JSON will settle whether 05 is a job task.
- **Runtime.** The README notebook says Serverless, Python 3.10. Local
  development uses 3.11 (handoff Section 2.9) until the runtime is confirmed.
