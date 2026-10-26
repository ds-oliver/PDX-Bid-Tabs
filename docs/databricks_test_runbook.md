# Databricks test runbook (Gate 2c)

**For:** Carrie (Port IT) and Hogan. **Status:** prepared, not run.

Gate 2c runs the reference pipeline and the refactored pipeline on Databricks,
each in its own isolated schema, on the same frozen inputs, and compares the
results with each other and with production. It comes after Gate 2b (local run
on production inputs) and before any cutover. Nothing here writes to
`pop-poc`.`bidtab` or `/Volumes/pop-poc/bidtab/`.

## 1. Choose isolated names

Values are pending Port IT. The examples below use these placeholders:

| Purpose | Example |
|---|---|
| Schema for the reference run | `` `pop-poc`.`bidtab_gate2c_ref` `` |
| Schema for the refactored run | `` `pop-poc`.`bidtab_gate2c_rf` `` |
| Volume holding frozen inputs and both runs' exports | `/Volumes/pop-poc/bidtab_gate2c/` |

## 2. Freeze the inputs

Right after a normal production run (so production tables reflect the same
inputs), copy the inputs into the isolated volume, once per run folder:

```python
for run in ["ref", "rf"]:
    for vol in ["source_files", "config"]:
        dbutils.fs.cp(f"/Volumes/pop-poc/bidtab/{vol}", f"/Volumes/pop-poc/bidtab_gate2c/{run}/{vol}", recurse=True)
```

Copying production's `exports/` too gives a third comparison point:
`/Volumes/pop-poc/bidtab_gate2c/prod_exports/`.

## 3. Deploy the code

Choose one; the choice is Port IT's (see `docs/refactor_notes.md`).

- **Git folder:** create a Databricks Git folder from the branch under test. The
  notebooks in `notebooks/` add `../src` to `sys.path`, so they import the
  package with no install step.
- **Wheel:** run `pip wheel . --no-deps -w dist/` locally, upload the wheel to a
  volume, and add it to the job environment. The bootstrap cell then has no
  effect.

For the reference run, generate rewritten copies of the reference notebooks
locally and upload them to a scratch workspace folder (do not commit them):

```bash
python tools/make_isolated_reference.py --table-prefix '`pop-poc`.`bidtab_gate2c_ref`' --volume-root /Volumes/pop-poc/bidtab_gate2c/ref --out build/isolated_reference
```

## 4. Dependencies

| Dependency | Needed by | In the production environment? |
|---|---|---|
| `pandas==2.3.3`, `openpyxl==3.1.5` | xlsx path | Yes (`requirements.txt`) |
| `pyspark` | everything | Yes (platform) |
| `bidtab_pipeline` (this repo) | refactored notebooks | No: Git folder path or wheel (step 3) |
| `pdfplumber` and its dependencies (`pdfminer.six`, `pypdfium2`, `Pillow`, `charset-normalizer`, `cryptography`) | PDF path only | No |
| `delta-spark`, `pytest`, `ruff` | local development only | Not needed |

**PyPI access on the Port workspace needs confirmation.** The PDF path cannot
run without `pdfplumber`. If the workspace cannot reach PyPI, the packages must
come from an internal mirror or be uploaded as wheels to a volume.

## 5. Run

Create two jobs (or one-time runs) with the same five tasks and order as
`resources/bidtab_job.yml`.

**Reference run:** tasks point at the rewritten notebooks from step 3. No
parameters; the targets are written into the code.

**Refactored run:** tasks point at `notebooks/` in the Git folder (or the wheel
job). Job parameters (they reach each notebook as widgets):

| Parameter | Value |
|---|---|
| `bidtab_table_prefix` | `` `pop-poc`.`bidtab_gate2c_rf` `` |
| `bidtab_volume_root` | `/Volumes/pop-poc/bidtab_gate2c/rf` |
| `bidtab_exports_root` | `/Volumes/pop-poc/bidtab_gate2c/rf/exports` |
| `bidtab_allow_production_write` | leave unset (false) |

With these, the write guard passes because every target is isolated. If any
parameter is missed, the package refuses to write to production and the task
fails with `ProductionWriteRefused`; that is the intended behavior.

## 6. Expected outputs

In each isolated schema: `bronze_raw_rows`, `silver_bid_items`,
`ref_awarded_bids`, `int_crosswalk`, `mart_bid_analysis`, the
`crosswalk_unmapped_items` view, `pipeline_run_log`, and `pipeline_file_log`.
In each run's `exports/`: the six CSVs. Each task's output shows the same job
log, Run Health Summary, and Delta report as production (the Delta report shows
every file as NEW on a first run in a fresh schema).

## 7. Compare

Download the export folders, then from the repo root:

```bash
python tools/compare_exports.py ./gate2c/ref_exports ./gate2c/rf_exports
```

```bash
python tools/compare_exports.py ./gate2c/prod_exports ./gate2c/rf_exports
```

The first must report `identical`. The second should be identical too if the
inputs did not change between the production run and the freeze; record any
differences rather than forcing a match. `tools/compare_exports.py` uses the
same normalization as the local tests: load timestamps excluded, arrays and rows
sorted.

Also compare the Run Health Summary and the Delta report displays by eye, and
the row counts of `pipeline_run_log` and `pipeline_file_log` (one run each).

## 8. Clean up

Drop both isolated schemas and the `bidtab_gate2c` volume when Gate 2c is
recorded. Do not keep the rewritten reference notebooks in the workspace.
