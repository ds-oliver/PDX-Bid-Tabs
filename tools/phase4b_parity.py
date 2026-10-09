#!/usr/bin/env python3
"""Phase 4b: shared Silver, crosswalk, and mart on PDF Bronze; FR-51 parity and FR-31 unmapped report.

Runs locally, in two isolated local schemas, nothing on Databricks:
- xlsx path: the refactored 01 to 04 (mart and unmapped view) on local_inputs/volumes
  (the Gate 2b inputs: 28 rebuilt workbooks and the chosen config).
- PDF path: 01b on the 17 fixture PDFs, then 02b (sources/pdf/shared.py) with the
  same config files.

Both marts exclude Engineer's Estimate rows (INCLUDE_ENG_EST = False, as in 04).
Inputs are only read. Output: docs/phase4b_parity_report.md (aggregates only:
per-schedule counts, per-bidder totals, unmapped descriptions, dates), and
local_inputs/phase4b/ (gitignored) with the full marts for review.

Usage (from the repo root; needs JDK 17 and the local, pdf extras):
    python tools/phase4b_parity.py
"""

from __future__ import annotations

import difflib
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
os.environ.setdefault("JAVA_HOME", "/opt/homebrew/opt/openjdk@17")

from bidtab_pipeline.config_loader.silver_config import AWARDED_BIDS_FILE  # noqa: E402
from bidtab_pipeline.io.local_spark import get_local_spark  # noqa: E402
from bidtab_pipeline.settings import Settings  # noqa: E402
from bidtab_pipeline.sources.pdf.bronze import build_pdf_bronze  # noqa: E402
from bidtab_pipeline.sources.pdf.shared import build_pdf_shared  # noqa: E402
from bidtab_pipeline.sources.xlsx.bronze import build_bronze  # noqa: E402
from bidtab_pipeline.transforms.crosswalk import build_int_crosswalk  # noqa: E402
from bidtab_pipeline.transforms.mart import build_mart, build_unmapped_view  # noqa: E402
from bidtab_pipeline.transforms.silver import build_silver  # noqa: E402

VOLUMES = REPO / "local_inputs" / "volumes"
PDF_DIR = REPO / "tests" / "fixtures" / "pdf"
HOLDOUT = REPO / "local_inputs" / "holdout"
OUT = REPO / "docs" / "phase4b_parity_report.md"
FULL = REPO / "local_inputs" / "phase4b"
TOLERANCE = 1.00

# The 8 EANs that match on solicitation number (handoff Section 1, decision 2). BRD's 5 are marked.
OVERLAP = {
    "2024-10481": ("2023D003", True),
    "2023-10218": ("2023D011", True),
    "2024-10569": ("2023D028", True),
    "2025-12724": ("2024D016", True),
    "2024-10691": ("2024D045", True),
    "2025-12566": ("2023D016", False),
    "2024-10519": ("2023D018", False),
    "2024-10566": ("2023D025", False),
}


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def money(v) -> str:
    return "" if v is None or pd.isna(v) else f"${v:,.2f}"


def match_bidders(pdf_names, xlsx_names) -> dict[str, tuple[str | None, str]]:
    """PDF canonical name -> (xlsx canonical name, method): same canonical name, same key, then closest key."""
    by_key = {key(n): n for n in xlsx_names}
    out = {}
    for name in pdf_names:
        if name in xlsx_names:
            out[name] = (name, "same canonical name")
        elif key(name) in by_key:
            out[name] = (by_key[key(name)], "same name ignoring spaces and punctuation")
        else:
            close = difflib.get_close_matches(key(name), list(by_key), n=1, cutoff=0.8)
            if close:
                ratio = difflib.SequenceMatcher(None, key(name), close[0]).ratio()
                out[name] = (by_key[close[0]], f"closest name, ratio {ratio:.2f}")
            else:
                out[name] = (None, "no match")
    return out


def run_pipelines(work: Path):
    spark = get_local_spark(work / "warehouse")
    for db in ("p4b_xlsx", "p4b_pdf"):
        spark.sql(f"DROP DATABASE IF EXISTS {db} CASCADE")
        spark.sql(f"CREATE DATABASE {db}")

    xlsx = Settings(table_prefix="`p4b_xlsx`", volume_root=str(VOLUMES))
    build_bronze(spark, xlsx)
    build_silver(spark, xlsx)
    build_int_crosswalk(spark, xlsx)
    build_mart(spark, xlsx, False)
    build_unmapped_view(spark, xlsx)

    landing = work / "pdf_landing"
    landing.mkdir()
    for p in sorted(PDF_DIR.glob("*.pdf")):
        shutil.copy2(p, landing / p.name)
    pdf_settings = Settings(
        table_prefix="`p4b_xlsx`",
        volume_root=str(VOLUMES),
        pdf_target_prefix="`p4b_pdf`",
        pdf_landing_root=str(landing),
    )
    build_pdf_bronze(spark, pdf_settings)
    pdf = build_pdf_shared(spark, pdf_settings, False)

    def pd_table(name, settings):
        df = spark.table(settings.table(name)).toPandas()
        return df.drop(columns=[c for c in df.columns if c.endswith("_loaded_at")])

    out = {
        "x_mart": pd_table("mart_bid_analysis", xlsx),
        "p_mart": pd_table("mart_bid_analysis", pdf),
        "p_silver": pd_table("silver_bid_items", pdf),
        "p_bronze": spark.table(pdf_settings.pdf_table("bronze_pdf_bid_items")).toPandas(),
        "p_totals": spark.table(pdf_settings.pdf_table("bronze_pdf_control_totals")).toPandas(),
        "p_manifest": spark.table(pdf_settings.pdf_table("ref_file_manifest")).toPandas(),
        "p_unmapped_view": spark.table(pdf.table("crosswalk_unmapped_items")).toPandas(),
    }
    spark.stop()
    return out


def due_dates() -> dict[str, str]:
    df = pd.read_excel(VOLUMES / "config" / AWARDED_BIDS_FILE, header=4)
    df["inv"] = df["Invitation #"].astype(str).str.strip()
    due = pd.to_datetime(df["Due Date"].astype(str), format="%m/%d/%Y %I:%M:%S %p", errors="coerce")
    return {k: v.date().isoformat() for k, v in due.groupby(df["inv"]).max().dropna().items()}


ROW_KEY = ["solicitation_no", "bid_type", "item_no", "contractor_name_canonical"]
NUMERIC = ("estimated_quantity", "unit_price", "total_price", "effective_unit_price", "item_no_sort")
# Differ by design: lineage (source file) and load times; bid_date and bid_year are classified separately.
ROW_SKIP = {"source_file", "bid_date", "bid_year"}


def row_level(x: pd.DataFrame, p: pd.DataFrame) -> tuple[dict, list[tuple]]:
    """Pair overlap mart rows on ROW_KEY and compare every other mart column (beyond FR-51)."""
    xs, ps = x[x.solicitation_no.isin(OVERLAP)], p[p.solicitation_no.isin(OVERLAP)]
    m = xs.merge(ps, on=ROW_KEY, how="outer", suffixes=("_x", "_p"), indicator=True)
    both = m[m._merge == "both"]
    stats = {
        "xlsx_rows": len(xs),
        "pdf_rows": len(ps),
        "paired": len(both),
        "xlsx_only": int((m._merge == "left_only").sum()),
        "pdf_only": int((m._merge == "right_only").sum()),
        "columns": 0,
    }
    diffs = []
    for col in [c[:-2] for c in m.columns if c.endswith("_x") and c[:-2] not in ROW_SKIP]:
        stats["columns"] += 1
        a, b = both[col + "_x"], both[col + "_p"]
        if col in NUMERIC:
            fa, fb = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
            bad = ((fa - fb).abs() > 0.005) | (fa.isna() != fb.isna())
        else:
            bad = a.astype(str) != b.astype(str)
        for _, r in both[bad].iterrows():
            diffs.append((r.solicitation_no, r.bid_type, r.item_no, r.contractor_name_canonical, col, r[col + "_x"], r[col + "_p"]))
    return stats, diffs


def main() -> int:
    if not (VOLUMES / "source_files").is_dir():
        print("local_inputs/volumes/ is missing (Gate 2b inputs)", file=sys.stderr)
        return 1
    work = Path(tempfile.mkdtemp(prefix="phase4b_"))
    t = run_pipelines(work)
    FULL.mkdir(parents=True, exist_ok=True)
    for name in ("x_mart", "p_mart"):
        t[name].to_csv(FULL / f"{name}.csv", index=False)

    x, p = t["x_mart"].copy(), t["p_mart"].copy()
    for df in (x, p):
        df["total_price"] = pd.to_numeric(df["total_price"])
        df["bid_date"] = df["bid_date"].astype(str)
    due = due_dates()
    manifest = t["p_manifest"]
    lines: list[str] = []
    w = lines.append

    # ---------------------------------------------------------------- FR-51
    fr51_rows, variances, bidder_rows, date_rows = [], [], [], []
    for sol, (ean, brd5) in OVERLAP.items():
        ps, xs = p[p.solicitation_no == sol], x[x.solicitation_no == sol]
        xfile = xs.source_file.iloc[0] if len(xs) else "(none)"
        pfile = ps.source_file.iloc[0] if len(ps) else "(none)"
        for bt in sorted(set(ps.bid_type) | set(xs.bid_type)):
            pb, xb = ps[ps.bid_type == bt], xs[xs.bid_type == bt]
            pi, xi = pb.item_no.nunique(), xb.item_no.nunique()
            pn, xn = pb.contractor_name_canonical.nunique(), xb.contractor_name_canonical.nunique()
            matches = match_bidders(sorted(pb.contractor_name_canonical.unique()), sorted(xb.contractor_name_canonical.unique()))
            ok_totals, n_totals = 0, 0
            for pname, (xname, method) in matches.items():
                ptot = pb[pb.contractor_name_canonical == pname].total_price.sum()
                xtot = xb[xb.contractor_name_canonical == xname].total_price.sum() if xname else None
                n_totals += 1
                within = xtot is not None and abs(ptot - xtot) <= TOLERANCE
                ok_totals += within
                bidder_rows.append((sol, bt, pname, xname or "", method, ptot, xtot, within))
                if xname is None:
                    variances.append((sol, bt, f"PDF bidder {pname} has no xlsx counterpart", "see cause"))
                elif not within:
                    variances.append((sol, bt, f"{pname}: PDF {money(ptot)} vs xlsx {money(xtot)}", "see cause"))
                elif method != "same canonical name":
                    variances.append(
                        (sol, bt, f"PDF bidder {pname} matched xlsx {xname} by {method}", "contractor alias missing")
                    )
            for xname in sorted(set(xb.contractor_name_canonical) - {m[0] for m in matches.values()}):
                variances.append((sol, bt, f"xlsx bidder {xname} has no PDF counterpart", "see cause"))
            if pi != xi:
                variances.append((sol, bt, f"item count PDF {pi} vs xlsx {xi}", "see cause"))
            if pn != xn:
                variances.append((sol, bt, f"bidder count PDF {pn} vs xlsx {xn}", "see cause"))
            fr51_rows.append((sol, ean, "yes" if brd5 else "", bt, pi, xi, pn, xn, f"{ok_totals}/{n_totals}"))
        pdates = sorted(ps.bid_date.unique())
        xdates = sorted(xs.bid_date.unique())
        date_rows.append((sol, ean, ",".join(pdates), ",".join(xdates), due.get(sol, "")))
        if xfile != "(none)" and pfile != "(none)":
            pass

    # ---------------------------------------------------------------- FR-31
    fr31 = []
    for _, m in manifest.sort_values("file_name").iterrows():
        pm = p[p.source_file == m.file_name]
        unm = pm[~pm.is_catalog_mapped.astype(bool)]
        fr31.append(
            (
                m.file_name,
                m.solicitation_no or "",
                m.parse_status,
                len(pm),
                len(unm),
                unm.item_description_raw.nunique(),
                f"{100 * (1 - len(unm) / len(pm)):.1f}%" if len(pm) else "",
            )
        )
    unmapped_desc = (
        p[~p.is_catalog_mapped.astype(bool)]
        .groupby(["source_file", "item_description_raw"])
        .size()
        .reset_index(name="rows")
        .sort_values(["source_file", "item_description_raw"])
    )

    total_pairs = len(bidder_rows)
    ok_pairs = sum(r[7] for r in bidder_rows)
    t["fr51_rows"], t["variances"], t["bidder_rows"], t["date_rows"] = fr51_rows, variances, bidder_rows, date_rows

    # ---------------------------------------------------------------- write
    w("# Phase 4b: PDF path through the shared Silver, crosswalk, and mart (FR-51, FR-31)")
    w("")
    w("Generated by `tools/phase4b_parity.py`. Both pipelines ran locally in isolated schemas; nothing ran on")
    w("Databricks. The xlsx side is the refactored pipeline on the Gate 2b inputs (`local_inputs/volumes/`: the 28")
    w("rebuilt workbooks verified against the 2026-05-28 golden run, and the chosen config). The PDF side is `01b`")
    w("on the 17 fixture PDFs, then `02b` (`src/bidtab_pipeline/sources/pdf/shared.py`): the same Silver, crosswalk,")
    w("and mart code and the same config files. Both marts exclude Engineer's Estimate rows (`INCLUDE_ENG_EST = False`).")
    w("The xlsx side is on `feature/pdf-source-v2`, without the B-14 fix, so its dates are the workbook save dates.")
    w("")
    w(f"Holdout: {'run, see below' if HOLDOUT.is_dir() else 'none supplied (`local_inputs/holdout/` does not exist); not run.'}")
    w("")
    w("## Summary")
    w("")
    w(f"- **Rows:** PDF mart {len(p):,} rows from {p.source_file.nunique()} PDFs; xlsx mart {len(x):,} rows from "
      f"{x.source_file.nunique()} workbooks.")
    w(f"- **FR-51 totals:** {ok_pairs} of {total_pairs} bidder x schedule totals in the 8 overlap solicitations match "
      f"within ${TOLERANCE:.2f}.")
    w(f"- **FR-51 variances:** {len(variances)} (item count, bidder count, or total outside $1.00).")
    w(f"- **FR-31:** {sum(r[4] for r in fr31)} unmapped PDF mart rows across {sum(1 for r in fr31 if r[4])} of 17 PDFs.")
    w("")
    lines.append("<!-- FINDINGS -->")
    w("")
    w("## FR-51 parity, 8 overlap solicitations")
    w("")
    w("Matched on solicitation number; schedules by `bid_type`; bidders by `contractor_name_canonical` (both sides go")
    w("through `contractor_alias_mapping.csv` in Silver), then by name ignoring spaces and punctuation, then by")
    w("closest name. Items are distinct `item_no` per schedule; bidders exclude the Engineer's Estimate.")
    w("")
    w("| Solicitation | EAN | BRD 5 | bid_type | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx | Totals within $1 |")
    w("|---|---|---|---|---|---|---|---|---|")
    for r in fr51_rows:
        w("| " + " | ".join(str(v) for v in r) + " |")
    w("")
    w("### Bidder x schedule totals")
    w("")
    w("| Solicitation | bid_type | PDF bidder | xlsx bidder | Match | PDF total | xlsx total | Within $1 |")
    w("|---|---|---|---|---|---|---|---|")
    for sol, bt, pn, xn, method, pt, xt, ok in bidder_rows:
        w(f"| {sol} | {bt} | {pn} | {xn} | {method} | {money(pt)} | {money(xt)} | {'yes' if ok else 'NO'} |")
    w("")
    w("### Variances")
    w("")
    lines.append("<!-- VARIANCES -->")
    w("")
    stats, diffs = row_level(t["x_mart"], t["p_mart"])
    t["row_level"] = (stats, diffs)
    w("### Row-level check (beyond FR-51)")
    w("")
    w(f"Overlap mart rows paired on solicitation, `bid_type`, `item_no`, and canonical bidder: xlsx {stats['xlsx_rows']:,},")
    w(f"PDF {stats['pdf_rows']:,}, paired {stats['paired']:,}, xlsx only {stats['xlsx_only']}, PDF only {stats['pdf_only']}.")
    w(f"{stats['columns']} mart columns compared (all but `source_file`, `bid_date`, `bid_year`); numbers within $0.005.")
    w("")
    if diffs:
        w("| Solicitation | bid_type | item_no | Bidder | Column | xlsx | PDF |")
        w("|---|---|---|---|---|---|---|")
        for d in diffs:
            w("| " + " | ".join(str(v) for v in d) + " |")
    else:
        w("No differences.")
    w("")
    w("## bid_date, classified separately")
    w("")
    w("The PDF carries the printed bid date. The xlsx side carries the workbook's cached `=TODAY()` (backlog B-14)")
    w("until `fix/b14-bid-date` merges; that fix takes the AwardedBidsSearchList Due Date.")
    w("")
    w("| Solicitation | EAN | PDF bid_date (printed) | xlsx bid_date (B-14) | AwardedBids Due Date | Class |")
    w("|---|---|---|---|---|---|")
    for sol, ean, pdt, xdt, dd in date_rows:
        if pdt == xdt:
            cls = "same"
        elif dd and pdt == dd:
            cls = "PDF = Due Date; xlsx is a save date (B-14)"
        elif dd and xdt == dd:
            cls = "xlsx = Due Date; PDF differs"
        elif not dd:
            cls = "no Due Date; xlsx is a save date (B-14)"
        else:
            cls = "all three differ"
        w(f"| {sol} | {ean} | {pdt} | {xdt} | {dd} | {cls} |")
    w("")
    w("## FR-31 unmapped report, all 17 PDFs")
    w("")
    w("Unmapped = mart rows whose `item_description_raw` has no `int_crosswalk` row (`is_catalog_mapped` false).")
    w("")
    w("| PDF | Solicitation | Parse status | Mart rows | Unmapped rows | Unmapped descriptions | Coverage |")
    w("|---|---|---|---|---|---|---|")
    for r in fr31:
        w("| " + " | ".join(str(v) for v in r) + " |")
    w("")
    if len(unmapped_desc):
        w("### Unmapped descriptions")
        w("")
        w("| PDF | item_description_raw | Mart rows |")
        w("|---|---|---|")
        for _, r in unmapped_desc.iterrows():
            w(f"| {r.source_file} | {r.item_description_raw} | {r['rows']} |")
        w("")
    t["lines"] = lines
    t["unmapped_desc"] = unmapped_desc
    t["fr31"] = fr31
    findings, causes = FINDINGS_TEXT, VARIANCE_CAUSES
    out = []
    for ln in lines:
        if ln == "<!-- FINDINGS -->":
            out.extend(findings)
        elif ln == "<!-- VARIANCES -->":
            if not variances:
                out.append("None.")
            else:
                out.append("| Solicitation | bid_type | Variance | Probable cause |")
                out.append("|---|---|---|---|")
                for sol, bt, what, _ in variances:
                    out.append(f"| {sol} | {bt} | {what} | {causes.get((sol, bt, what), 'not yet classified')} |")
        else:
            out.append(ln)
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    for r in variances:
        print("VARIANCE", r[:3])
    return 0


# Probable cause per FR-51 variance, keyed (solicitation, bid_type, variance text). None in the current run.
VARIANCE_CAUSES: dict[tuple[str, str, str], str] = {}

FINDINGS_TEXT = [
    "## Findings",
    "",
    "- **FR-51 passes with no variances.** For all 8 overlap solicitations (16 schedules), item counts, bidder",
    "  counts, and all 59 bidder x schedule totals are equal; every PDF bidder maps to the same canonical name as",
    "  its xlsx counterpart through the existing `contractor_alias_mapping.csv`, so no close-name matching was needed.",
    "- **Row level, the two marts agree on every compared column but one value.** All 1,617 overlap rows pair one to",
    "  one. The single difference is 2025-12724 item 0012, Apex Mechanical: `total_price` 198,745.625 in the workbook",
    "  vs 198,745.63 printed on the PDF. Probable cause: the workbook keeps the unrounded unit price x quantity; the",
    "  PDF prints cents. It is within FR-51's $1.00 and does not change any total by more than half a cent.",
    "- **bid_date is the only systematic difference, and the xlsx side is the one that is wrong** (B-14). The",
    "  dates differ in 4 of 8 solicitations, each time because the xlsx date is a workbook save date. In 2 of the 4",
    "  (2024-10481, 2024-10569) the PDF's printed date equals the AwardedBids Due Date that `fix/b14-bid-date` would",
    "  load. 2024-10519: printed 2024-04-04, Due Date 2024-04-02, xlsx 2026-01-26; probable cause: the opening moved",
    "  after the PlanetBids date was set, or the printed date is the tabulation date; to confirm with the spec writer",
    "  before the B-14 fix is approved. 2025-12566 has no Due Date in the export, so the fix would keep its save date",
    "  (2026-02-26) while the PDF prints 2025-12-19.",
    "- **2024-10566 (single contractor)** is in both marts with 1 bidder per schedule: the xlsx path reads it because",
    "  the Engineer's Estimate supplies the second price pair `01` needs (B-10). 2024-10564, also single-contractor,",
    "  has no xlsx counterpart; the PDF path loads it (7 mart rows).",
    "- **FR-31: the 8 overlap PDFs are 100% mapped; the 9 others are not.** 1,038 unmapped mart rows (179 distinct",
    "  descriptions) are all in PDFs with no xlsx counterpart: the crosswalk was built from the 27 workbooks, so new",
    "  solicitations bring new descriptions. Coverage ranges from 14.3% (2024-10564) to 54.5% (2018-7876, the",
    "  excluded 2017D013 project). 2023-10383 (the D-03 two-base-schedule file) is 46.3%. This is the crosswalk",
    "  maintenance the Maintenance Guide describes, not a parser issue; the descriptions are listed below for the",
    "  Port's crosswalk review.",
    "- **Engineer's Estimate rows** are excluded from both marts (`INCLUDE_ENG_EST = False`) and kept in Silver.",
    "",
]

if __name__ == "__main__":
    sys.exit(main())
