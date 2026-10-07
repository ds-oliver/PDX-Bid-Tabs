# Legacy: March 2026 local pandas package

This is the `bidtabs` package, CLI scripts, and tests that were on `main` until
the 2026-05-28 Databricks baseline was recovered. It is **not** the production
pipeline and not the xlsx path for the refactor. The production baseline is
`reference/databricks_2026-05-28/`.

Kept for reference. Moved with `git mv`, so history is intact.

## Running the tests

From the repo root:

```bash
pip install -e ".[dev,legacy]"
pytest legacy/local_pandas_v0/tests
```

The tests call scripts with relative paths and overwrite what they find in
`data_out/`, `reports/`, and `docs/`. `tests/conftest.py` runs the whole session
in a scratch copy of those directories, so the tracked files are never touched.

Two tests are marked as expected failures: `build_dashboard_field_mapping.py`
now writes an `ODOT_to_Port_Mapping` workbook, and the tests still expect
`README` and `Field_Mapping` sheets.
