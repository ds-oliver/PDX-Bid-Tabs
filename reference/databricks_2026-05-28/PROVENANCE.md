# Provenance: Databricks baseline, 2026-05-28

These notebooks are the xlsx-path reference implementation. They are decoded
from Databricks HTML exports and committed unchanged. Do not edit them; the
refactored package must reproduce their behavior.

## Source run

| Item | Value |
|---|---|
| Job | `bidtab_pipeline_full_refresh` |
| Run | 2026-05-28, 21:06:59 to 21:11:44 UTC (from cell start and finish times in the exports) |
| run_id | `f2a96410` (from the 2026-10-07 handoff and `golden_run_2026-05-28.json`; the HTML exports do not contain it) |
| Decoder | `tools/decode_databricks_html.py` |
| Check | `python tools/decode_databricks_html.py --verify` prints `OK` for all six files |

## Files

Source paths are on Hogan's Mac. The HTML files are not committed (no run
HTML in Git).

| Decoded file | Source HTML | Source HTML SHA-256 | Decoded SHA-256 | Cell times (UTC) |
|---|---|---|---|---|
| `notebooks/01_parse_single_bidtab.py` | `~/Downloads/notebook01_bronze_pipeline_run.html` | `3f9c7951b4b8b077f400d0c543e4831d6336ceaa60903ce1e15c32e193cb3f7e` | `7325468ad7666dfe30d82c08eaba2403da21f211f2af0e1bd3ac8529e0c3c63d` | 2026-05-28 21:06:59 to 21:07:22 |
| `notebooks/02_build_silver.py` | `~/Downloads/notebook02_silver_pipeline_run.html` | `38c2fb7ccba152a6c3676082e23902f91a5053bbf161d93a5f8fe351dce120de` | `02fcc89aee45d1f72067f72da20356b55a80ba75b39780ead7bb9cdca0fc67b6` | 2026-05-28 21:07:53 to 21:08:44 |
| `notebooks/03_load_crosswalk.py` | `~/Downloads/notebook03_load_xwalk_pipeline_run.html` | `8fb2b183baa427c1f66c20522183fc76acb15bc90d849f13e94f0a242c792f47` | `13ec6ef53a2d304417750829c6d20a60d59ea5cbd67697387b6d795d7f4d99bc` | 2026-05-28 21:09:07 to 21:09:21 |
| `notebooks/04_build_mart.py` | `~/Downloads/notebook04_build_mart_pipeline_run.html` | `2fca2ce0ed2e320a5c8ac1e6ba83d9573d19250a346cf7c1f67a1aad70db264c` | `e438855f21474b4f87f1ee323345ab408637729a3c0d87a9ff5aa3fb84ff91cd` | 2026-05-28 21:09:49 to 21:10:31 |
| `notebooks/05_export_csvs.py` | `~/Downloads/notebook05_export_csvs_pipeline_run.html` | `b6aaa4f2f0d581b97b8ebc8a473b8e7cdc372f04bdece7e4ccacc70e26049d91` | `913702df8d454e39d40c39dd9c6c2eb236e1d7ae188e496abb093b45442de62e` | 2026-05-28 21:11:12 to 21:11:44 |
| `notebooks/README.py` | `~/Downloads/Src (final3)/README.html` | `9560c186b453cd2e850f61650d51eb4ea8ed380f61246b32d0f060a479130f4d` | `9a43e91cd8003fafbbee6eac49b94bd29015a58a7b36157827d913d269b331a5` | not a run export (saved 2026-05-22) |

## Notes

- **04 source file.** The decoder as supplied read `04` from
  `notebook04_build_mart_pipeline_run_20260603.html`. That file is a different
  run: its cells executed 2026-05-30 01:09 UTC. The 2026-05-28 run's own `04`
  export is `notebook04_build_mart_pipeline_run.html`; its notebook origId
  (`1184170017993808`) falls in sequence with 01, 02, 03 and 05. Both files
  decode to the same source hash, so the code is identical. The repo copy of
  the decoder reads the 2026-05-28 file.
- **Other 04 export.** `notebook04_build_mart_pipeline_run_file_excluded.html`
  (2026-05-28 21:49 UTC, after the job run) also decodes to the same source.
- **README.** `README.py` is the workspace README notebook from the
  `Src (final3)` export, not part of the job run. It describes the job and
  states the `requirements.txt` pins (`openpyxl==3.1.5`, `pandas==2.3.3`).
- **Decoder fidelity.** Checked 2026-10-06 against a native Databricks `.py`
  export (`Src Build (final2)`): byte-identical for 01, 03, 04. For 02 the
  only difference is one trailing empty cell that the HTML export omits.
- **Pending confirmation.** If the Port's export of
  `/Workspace/Shared/Bidtab/Src/` differs from these files, it replaces this
  baseline (handoff Section 5, item 1).
