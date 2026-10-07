# Databricks notebook source
# MAGIC %md
# MAGIC # Bid Tab Analytics Pipeline — README
# MAGIC
# MAGIC **Project:** Searchable Historical Bid Tab Database & Cost Trend Reporting
# MAGIC **Client:** Port of Portland — Engineering Innovation & Digital Center
# MAGIC **Delivered by:** PSU MS-ADSB Capstone Team (May 2026)
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## What this pipeline does
# MAGIC
# MAGIC Transforms historical construction bid tab Excel workbooks into a single Power BI–ready analytical table. Source data is matrix-style (one workbook per project, items as rows, contractors as columns). The pipeline reshapes this into a row-level dataset at the grain of **one row per project × bid tab section × pay item × contractor**, with descriptions standardized against the Port's Hard Cost Estimate Form catalog.
# MAGIC
# MAGIC The output table `pop-poc.bidtab.mart_bid_analysis` is the single source consumed by the Power BI dashboard.
# MAGIC
# MAGIC ## Architecture
# MAGIC
# MAGIC Standard medallion pattern, four stages:
# MAGIC
# MAGIC | Stage | Notebook | Output Table | Purpose |
# MAGIC |---|---|---|---|
# MAGIC | Bronze | `01_parse_single_bidtab` | `bronze_raw_rows` | Parses every `.xlsx` in the source volume; auto-detects canonical sheet names |
# MAGIC | Silver | `02_build_silver` | `silver_bid_items` | Cleans descriptions, standardizes contractor names, joins awarded bids, applies QA flags |
# MAGIC | Crosswalk | `03_load_crosswalk` | `int_crosswalk` | Loads the catalog CSV; auto-repairs cost codes; splits FAA vs Port codes |
# MAGIC | Mart | `04_build_mart` | `mart_bid_analysis` | Joins Silver to Crosswalk; produces the Power BI table and `crosswalk_unmapped_items` view |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Key locations
# MAGIC
# MAGIC ### Code
# MAGIC | What | Where |
# MAGIC |---|---|
# MAGIC | Pipeline notebooks (01–04) | This folder |
# MAGIC | `requirements.txt` | This folder |
# MAGIC
# MAGIC ### Data
# MAGIC | What | Path |
# MAGIC |---|---|
# MAGIC | Source bid tab workbooks | `/Volumes/pop-poc/bidtab/source_files/` |
# MAGIC | Configuration CSVs | `/Volumes/pop-poc/bidtab/config/` |
# MAGIC | Unity Catalog schema | `pop-poc.bidtab` |
# MAGIC
# MAGIC ### Config files (in `/Volumes/pop-poc/bidtab/config/`)
# MAGIC | File | Purpose |
# MAGIC |---|---|
# MAGIC | `Final_Recommended_Line_Item_List.csv` | Pay item crosswalk — every raw description maps to a catalog item |
# MAGIC | `contractor_alias_mapping.csv` | Collapses contractor name variants to a canonical name |
# MAGIC | `AwardedBidsSearchList.xlsx` | Reference list of awarded bids by solicitation number |
# MAGIC | `concat_fixes.csv` | Regex patterns to fix concatenated descriptions (e.g., `WORKZONEANDTRAFFICCONTROL`) |
# MAGIC | `text_normalization.csv` | Full-string regex aliases that fold description variants |
# MAGIC | `unit_mapping.csv` | Unit abbreviation standardizations (e.g., `Each` → `EA`) |
# MAGIC
# MAGIC ### Job
# MAGIC | What | Where |
# MAGIC |---|---|
# MAGIC | Job name | `bidtab_pipeline_full_refresh` |
# MAGIC | Job ID | `862352363834430` |
# MAGIC | Job URL | https://dbc-ccd7a07b-057f.cloud.databricks.com/jobs/862352363834430 |
# MAGIC
# MAGIC ### Downstream
# MAGIC | What | Where |
# MAGIC |---|---|
# MAGIC | Power BI dashboard | Port Power BI tenant — "Bid Tab Analytics" workspace |
# MAGIC | Power BI data source | `SQL-Serverless-X-Small-PowerBiOnly` warehouse → `pop-poc.bidtab.mart_bid_analysis` |
# MAGIC | Ingestion validation app (Streamlit) | Databricks Apps — `bidtab_pipeline` |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## How to run the pipeline
# MAGIC
# MAGIC 1. Sign in to Databricks
# MAGIC 2. **Workflows** (left sidebar) → click `bidtab_pipeline_full_refresh`
# MAGIC 3. Click **Run now** (top right)
# MAGIC 4. Wait ~3–4 minutes. All four tasks should turn green.
# MAGIC 5. Open Power BI and refresh the dataset
# MAGIC
# MAGIC The tasks run sequentially: 01 → 02 → 03 → 04. Each depends on the previous. Bronze uses `mode("overwrite")` so the job is idempotent and safe to re-run at any time.
# MAGIC
# MAGIC ## When to run it
# MAGIC
# MAGIC Run the pipeline after any of these changes:
# MAGIC - A new bid tab workbook uploaded to `source_files/`
# MAGIC - Any config CSV edited and re-uploaded
# MAGIC - The crosswalk file (`Final_Recommended_Line_Item_List.csv`) updated with new mappings
# MAGIC - A new contractor alias added
# MAGIC
# MAGIC ## Environment
# MAGIC
# MAGIC - **Compute:** Serverless (Autoscaling)
# MAGIC - **Python:** 3.10 (Standard v1 base environment)
# MAGIC - **Dependencies:** `openpyxl==3.1.5`, `pandas==2.3.3` — pinned in `requirements.txt`
# MAGIC - Each task uses `Notebook Environment` to inherit the pinned versions
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Documentation
# MAGIC
# MAGIC | Document | Purpose | Audience |
# MAGIC |---|---|---|
# MAGIC | `Bid_Tab_Pipeline_Maintenance_Guide.docx` | Step-by-step "how to maintain" reference — scenarios, troubleshooting, quick reference card | Port staff (no coding required) |
# MAGIC | `crosswalk_methodology.pdf` | Methodology behind the pay item crosswalk; classification rules; config file reference | Anyone editing the crosswalk |
# MAGIC | `Port_of_Portland_SOW_Final.docx` | Original scope document | Reference |
# MAGIC | This README | Code-side orientation; what lives where | Anyone opening the workspace folder |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Data dictionary — `mart_bid_analysis`
# MAGIC
# MAGIC See `Bid_Tab_Pipeline_Maintenance_Guide.docx`, Appendix A, for the full column-level data dictionary. The mart is a single denormalized table designed for Power BI Import mode — all dimensions are flattened.
# MAGIC
# MAGIC Three description layers exist on every row:
# MAGIC - `item_description_raw` — verbatim from the bid tab
# MAGIC - `item_description_normalized` — lightly cleaned (spacing, capitalization, unit symbols)
# MAGIC - `item_description_standardized` — fully standardized via the catalog crosswalk
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Common maintenance tasks
# MAGIC
# MAGIC For step-by-step procedures, see the **Maintenance Guide** (linked above). The most common scenarios:
# MAGIC
# MAGIC 1. **New bid tab workbook arrives** → upload to `source_files/`, run job, verify in Power BI
# MAGIC 2. **Unmapped pay items appear** → check `crosswalk_unmapped_items` view, add rows to `Final_Recommended_Line_Item_List.csv`, re-upload, run job
# MAGIC 3. **Contractor name variant** → add row to `contractor_alias_mapping.csv`, re-upload, run job
# MAGIC 4. **Pay item mapped incorrectly** → edit the existing row in `Final_Recommended_Line_Item_List.csv`, re-upload, run job
# MAGIC
# MAGIC ## Verifying a run
# MAGIC
# MAGIC After every job run, check these in order:
# MAGIC
# MAGIC | Check | Where | What to look for |
# MAGIC |---|---|---|
# MAGIC | All 4 tasks green | Workflows → job run history | Each task succeeded |
# MAGIC | Silver–Crosswalk join rate | `03_load_crosswalk` cell output | 100% match rate |
# MAGIC | Mart row count = Silver row count | `04_build_mart` cell output | `mart_vs_silver` check returns `PASS` |
# MAGIC | Unmapped items | Query `crosswalk_unmapped_items` view | Should be empty after first run |
# MAGIC | Power BI Data Quality page | Power BI dashboard | All three indicator cards green |
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Known design decisions
# MAGIC
# MAGIC A few choices that aren't obvious from the code, documented here so they're not relitigated later:
# MAGIC
# MAGIC - **No fuzzy matching in the crosswalk.** Tested early and rejected for high false positive rate in this domain. The crosswalk is a manually curated reference table.
# MAGIC - **`item_description_raw` is the join key.** Case-insensitive and trimmed, but otherwise exact. Hard-fail QA in notebook 03 prevents duplicate keys.
# MAGIC - **Cost code stored as a string with leading zeros preserved.** Auto-repair in notebook 03 pads 1–5 digit numeric values to 6 digits.
# MAGIC - **`PDX_2017D013.xlsx` is excluded** via the `SKIP_FILES` list in notebook 01 — it's a template workbook with no usable bid data.
# MAGIC - **Bronze uses `mode("overwrite")`.** Every run re-parses every workbook in `source_files/`. At current volume (~28 files, ~6,300 rows) this completes in seconds.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Adding a new dependency
# MAGIC
# MAGIC If the pipeline ever needs a new Python package:
# MAGIC
# MAGIC 1. Add it to `requirements.txt` with a pinned version (e.g., `package==1.2.3`)
# MAGIC 2. Restart any open notebook sessions
# MAGIC 3. The next job run will pick it up automatically
# MAGIC
# MAGIC All four task definitions point at `Notebook Environment`, which reads `requirements.txt`. Do not configure job-scoped environments — keep one source of truth.
# MAGIC
# MAGIC ---
# MAGIC
# MAGIC ## Support contact
# MAGIC
# MAGIC For technical issues with the pipeline after handoff: contact the Engineering Innovation & Digital Center analytics support resource. For data quality questions about specific bid items or contractors: Amanda Coleman, Engineering Innovation Manager.
# MAGIC