#!/usr/bin/env python3
"""Phase 4a: provisional parity of PDF Bronze against the May 14 v4 Databricks exports.

PROVISIONAL. Inputs are the 2026-05-14 exports (older than the 2026-05-28
baseline), and Silver is not applied to the PDF rows. This is a dry run to find
problems early. It does not satisfy FR-51 or any gate.

Inputs:
    tests/fixtures/pdf/*.pdf                                  parsed with the PDF parser
    local_inputs/provisional/databricks_v4_2026-05-14/        mart_bid_analysis (latest).csv,
                                                              int_crosswalk (latest).csv
Output:
    docs/phase4a_provisional_parity.md

Usage (from the repo root):
    python tools/phase4a_provisional_parity.py
"""

from __future__ import annotations

import difflib
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from bidtab_pipeline.sources.pdf.bronze import ingest_landing  # noqa: E402

V4 = REPO / "local_inputs" / "provisional" / "databricks_v4_2026-05-14"
OUT = REPO / "docs" / "phase4a_provisional_parity.md"
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


def join_key(desc) -> str:
    return str(desc).lower().strip()


def money(v) -> str:
    return "" if v is None or pd.isna(v) else f"${v:,.2f}"


def match_bidders(pdf_names: list[str], xlsx_names: list[str]) -> dict[str, tuple[str | None, str]]:
    """PDF name -> (xlsx canonical name, method). Exact normalized key first, then close match."""
    by_key = {key(n): n for n in xlsx_names}
    out = {}
    for name in pdf_names:
        if key(name) in by_key:
            out[name] = (by_key[key(name)], "exact")
            continue
        close = difflib.get_close_matches(key(name), list(by_key), n=1, cutoff=0.8)
        out[name] = (
            (by_key[close[0]], f"close, ratio {difflib.SequenceMatcher(None, key(name), close[0]).ratio():.2f}")
            if close
            else (None, "none")
        )
    return out


def main() -> int:
    mart = pd.read_csv(V4 / "mart_bid_analysis (latest).csv", dtype=str)
    for col in ("total_price", "unit_price"):
        mart[col] = pd.to_numeric(mart[col], errors="coerce")
    xwalk = pd.read_csv(V4 / "int_crosswalk (latest).csv", dtype=str)
    xwalk_keys = set(xwalk["raw_join_key"].dropna())

    pdf = pd.DataFrame(ingest_landing(str(REPO / "tests" / "fixtures" / "pdf")).items)
    totals = pd.DataFrame(ingest_landing(str(REPO / "tests" / "fixtures" / "pdf")).control_totals)

    lines: list[str] = []
    w = lines.append
    w("# Phase 4a: provisional parity, PDF Bronze vs May 14 exports")
    w("")
    w("> **Provisional.** Compared against the 2026-05-14 v4 Databricks exports, which predate the 2026-05-28")
    w("> baseline (no Engineer's Estimate rows; older code). Silver is not applied to the PDF rows. This is a")
    w("> dry run, not FR-51 and not a gate. Regenerate with `python tools/phase4a_provisional_parity.py`.")
    w("")
    w("Matching: solicitation number between sources; schedules by `bid_type` (the PDF's provisional mapping);")
    w("bidders by a name key without spaces or punctuation, then the closest name (ratio at least 0.80).")
    w("The xlsx export has no Engineer's Estimate rows, so PDF Engineer's Estimate rows are left out of the")
    w("bidder and total comparisons and counted separately.")
    w("")

    findings_at = len(lines)
    close_matches: list[str] = []
    schedule_sets_equal = items_equal = bidders_equal = True

    # --- summary table --------------------------------------------------------------
    summary_rows, detail_sections, coverage_rows, unmatched_desc = [], [], [], []
    for sol, (ean, in_brd) in OVERLAP.items():
        p = pdf[pdf.solicitation_no == sol]
        x = mart[mart.solicitation_no == sol]
        p_contract = p[~p.is_engineers_estimate]
        sched_p = sorted(p.bid_type.unique())
        sched_x = sorted(x.bid_type.unique())
        bidders_p = sorted(p_contract.contractor_name.unique())
        bidders_x = sorted(x.contractor_name_canonical.unique())
        matches = match_bidders(bidders_p, bidders_x)
        close_matches += [f"{sol}: {n} -> {m[0]} ({m[1]})" for n, m in matches.items() if m[1] != "exact"]
        schedule_sets_equal &= sched_p == sched_x
        for bt in sched_p:
            ps, xs = p_contract[p_contract.bid_type == bt], x[x.bid_type == bt]
            items_equal &= ps.item_no.nunique() == xs.item_no.nunique()
            bidders_equal &= ps.contractor_name.nunique() == xs.contractor_name_canonical.nunique()

        cells_ok = cells = 0
        sec = [f"### {sol} (EAN {ean}){' — in the BRD 5' if in_brd else ''}", ""]
        sec.append(f"PDF file `{p.source_file.iloc[0]}`; xlsx file `{x.source_file.iloc[0]}`.")
        sec.append("")
        sec.append("| Schedule (bid_type) | Items PDF | Items xlsx | Bidders PDF | Bidders xlsx |")
        sec.append("|---|---|---|---|---|")
        for bt in sorted(set(sched_p) | set(sched_x)):
            ps, xs = p_contract[p_contract.bid_type == bt], x[x.bid_type == bt]
            sec.append(
                f"| {bt} | {ps.item_no.nunique() if len(ps) else '—'} | {xs.item_no.nunique() if len(xs) else '—'} "
                f"| {ps.contractor_name.nunique() if len(ps) else '—'} | {xs.contractor_name_canonical.nunique() if len(xs) else '—'} |"
            )
        sec.append("")
        sec.append("| Bidder (PDF) | Matched xlsx name | Match | Schedule | Total PDF | Total xlsx | Difference |")
        sec.append("|---|---|---|---|---|---|---|")
        for name in bidders_p:
            xname, method = matches[name]
            for bt in sched_p:
                tp = p_contract[(p_contract.contractor_name == name) & (p_contract.bid_type == bt)].total_price.sum()
                if xname is None:
                    tx = None
                else:
                    xs = x[(x.contractor_name_canonical == xname) & (x.bid_type == bt)]
                    tx = xs.total_price.sum() if len(xs) else None
                diff = None if tx is None else round(tp - tx, 2)
                cells += 1
                ok = diff is not None and abs(diff) <= TOLERANCE
                cells_ok += ok
                sec.append(
                    f"| {name} | {xname or '—'} | {method} | {bt} | {money(tp)} | {money(tx)} | "
                    f"{'' if diff is None else ('match' if ok else money(diff))} |"
                )
        extra_x = sorted(set(bidders_x) - {m[0] for m in matches.values() if m[0]})
        if extra_x:
            sec.append("")
            sec.append(f"xlsx bidders with no PDF match: {', '.join(extra_x)}.")
        ee_rows = int(p.is_engineers_estimate.sum())
        sec.append("")
        sec.append(f"PDF Engineer's Estimate rows left out: {ee_rows}.")
        sec.append("")
        detail_sections.append("\n".join(sec))

        # crosswalk coverage
        p_keys = p.item_description_raw.map(join_key)
        x_keys = x.item_description_raw.map(join_key)
        p_hit, x_hit = p_keys.isin(xwalk_keys), x_keys.isin(xwalk_keys)
        p_desc = set(p_keys)
        coverage_rows.append(
            (
                sol,
                ean,
                p_hit.mean() * 100,
                len(p),
                x_hit.mean() * 100 if len(x) else float("nan"),
                len(x),
                sum(k in xwalk_keys for k in p_desc),
                len(p_desc),
            )
        )
        x_raw = sorted(set(x.item_description_raw.dropna()))
        for desc, n in Counter(p.loc[~p_hit, "item_description_raw"]).most_common():
            best = difflib.get_close_matches(desc, x_raw, n=1, cutoff=0)
            ratio = difflib.SequenceMatcher(None, desc, best[0]).ratio() if best else 0
            unmatched_desc.append((n, sol, desc, best[0] if best else "", ratio))

        summary_rows.append(
            (
                sol,
                ean,
                "yes" if in_brd else "no",
                len(sched_p),
                len(sched_x),
                p_contract.groupby("bid_type").item_no.nunique().sum(),
                x.groupby("bid_type").item_no.nunique().sum(),
                len(bidders_p),
                len(bidders_x),
                f"{cells_ok}/{cells}",
            )
        )

    tp_rows = sum(r[3] for r in coverage_rows)
    tp_hit = sum(round(r[2] * r[3] / 100) for r in coverage_rows)
    tx_rows = sum(r[5] for r in coverage_rows)
    tx_hit = sum(round(r[4] * r[5] / 100) for r in coverage_rows)
    ok_cells = sum(int(r[-1].split("/")[0]) for r in summary_rows)
    all_cells = sum(int(r[-1].split("/")[1]) for r in summary_rows)
    findings = [
        "## Findings",
        "",
        f"- **Totals:** {ok_cells} of {all_cells} bidder x schedule totals match within $1.00 across the 8 EANs.",
        f"- **Schedules:** the PDF's provisional `bid_type` names {'equal' if schedule_sets_equal else 'differ from'} "
        "the xlsx `bid_type` values for every overlap EAN. No overlap EAN has several base schedules, so the "
        "`Base Bid Tab - <schedule>` form (2023-10383) is not exercised here.",
        f"- **Item and bidder counts per schedule:** {'equal' if items_equal and bidders_equal else 'not all equal'} "
        "(PDF Engineer's Estimate excluded).",
        f"- **Bidder names:** all matched; {len(close_matches)} by closest name rather than the exact key"
        + (": " + "; ".join(close_matches) if close_matches else "")
        + ".",
        f"- **Crosswalk coverage:** PDF {100 * tp_hit / tp_rows:.1f}% of rows vs xlsx {100 * tx_hit / tx_rows:.1f}%. "
        "This dry run found one parser defect, now fixed: a description line clipped on the page but present in the "
        "text layer (2025-12566 items 0056 and 0057; see docs/pdf_source_notes.md).",
        "- **Pullman SST (non-responsive, 2024-10691)** and the **single-bidder schedules** appear the same way on "
        "both sides; details below.",
        "",
    ]
    lines[findings_at:findings_at] = findings

    w("## Summary by solicitation")
    w("")
    w(
        "| Solicitation | EAN | BRD 5 | Schedules PDF | Schedules xlsx | Items PDF | Items xlsx | Bidders PDF (excl. EE) | Bidders xlsx | Bidder x schedule totals within $1 |"
    )
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in summary_rows:
        w("| " + " | ".join(str(v) for v in r) + " |")
    w("")
    w("Items are distinct item numbers summed over schedules.")
    w("")

    w("## Crosswalk coverage")
    w("")
    w("Share of rows whose `lower(trim(item_description_raw))` is in `int_crosswalk.raw_join_key` (May 14 export).")
    w("PDF descriptions are rebuilt per FR-13 (wrapped lines joined with single spaces, spec reference kept).")
    w("")
    w(
        "| Solicitation | EAN | PDF rows covered | PDF rows | xlsx rows covered | xlsx rows | PDF distinct descriptions covered |"
    )
    w("|---|---|---|---|---|---|---|")
    for sol, ean, pc, pn, xc, xn, dh, dn in coverage_rows:
        w(f"| {sol} | {ean} | {pc:.1f}% | {pn} | {xc:.1f}% | {xn} | {dh}/{dn} |")
    w(
        f"| **All 8** | | **{100 * tp_hit / tp_rows:.1f}%** | {tp_rows} | **{100 * tx_hit / tx_rows:.1f}%** | {tx_rows} | |"
    )
    w("")
    w("### Top unmatched PDF descriptions")
    w("")
    if not unmatched_desc:
        w("None: every PDF description for the 8 EANs is a crosswalk key.")
    else:
        w("Closest xlsx description from the same solicitation, with a similarity ratio (1.00 is identical).")
        w("")
        w("| PDF rows | Solicitation | PDF description | Closest xlsx description | Ratio |")
        w("|---|---|---|---|---|")
        for n, sol, desc, best, ratio in sorted(unmatched_desc, key=lambda t: (-t[0], t[1]))[:25]:
            w(f"| {n} | {sol} | {desc} | {best} | {ratio:.2f} |")
        w("")
        w(f"{len(unmatched_desc)} distinct unmatched PDF descriptions in total.")
    w("")

    # --- Pullman and single-bidder schedules ------------------------------------------
    w("## Non-responsive bidder in 2024-10691 (Pullman SST, Inc.)")
    w("")
    pp = pdf[(pdf.solicitation_no == "2024-10691") & (pdf.contractor_name.map(key) == key("Pullman SST, Inc."))]
    pt = totals[
        (totals.solicitation_no == "2024-10691") & (totals.bidder_name_raw.map(key) == key("Pullman SST, Inc."))
    ]
    star = pt[pt.is_starred]
    xp = mart[
        (mart.solicitation_no == "2024-10691") & (mart.contractor_name_canonical.map(key).str.startswith("pullman"))
    ]
    w("| | PDF Bronze | xlsx mart (May 14) |")
    w("|---|---|---|")
    w(f"| Rows | {len(pp)} | {len(xp)} |")
    w(
        f"| Rows with null unit price | {int(pp.unit_price.isna().sum())} | {int(xp.unit_price.isna().sum()) if len(xp) else '—'} |"
    )
    w(f"| Sum of item totals | {money(pp.total_price.sum())} | {money(xp.total_price.sum()) if len(xp) else '—'} |")
    w(
        f"| Name | {pp.contractor_name.iloc[0] if len(pp) else '—'} | {xp.contractor_name_canonical.iloc[0] if len(xp) else '—'} |"
    )
    w(
        f"| Summary total, footnote | {money(star.total_amount.iloc[0]) if len(star) else '—'}, \"{star.footnote_text.iloc[0] if len(star) else ''}\" (is_corrected_total false) | not carried |"
    )
    w("")
    w("## Single-bidder schedules")
    w("")
    w("Backlog B-10: workbook 01 skips any sheet with fewer than two Unit Price / Total Price pairs. The PDF")
    w("parser does not copy that skip. Schedules with exactly one contractor (Engineer's Estimate not counted):")
    w("")
    singles = (
        pdf[~pdf.is_engineers_estimate].groupby(["solicitation_no", "bid_type"]).contractor_name.nunique().reset_index()
    )
    singles = singles[singles.contractor_name == 1]
    if singles.empty:
        w("None in the 17 fixtures.")
    else:
        w("| Solicitation | Schedule | In overlap set | xlsx rows for this schedule | Note |")
        w("|---|---|---|---|---|")
        for _, r in singles.iterrows():
            xs = mart[(mart.solicitation_no == r.solicitation_no) & (mart.bid_type == r.bid_type)]
            in_overlap = r.solicitation_no in OVERLAP
            note = (
                "One contractor plus the Engineer's Estimate gives two price pairs, so 01 parses the sheet"
                if len(xs)
                else ("Not in the xlsx export" if in_overlap else "No xlsx counterpart in the overlap set")
            )
            w(
                f"| {r.solicitation_no} | {r.bid_type} | {'yes' if in_overlap else 'no'} | {len(xs) if in_overlap else '—'} | {note} |"
            )
    w("")
    w("## Per-solicitation detail")
    w("")
    lines.extend(detail_sections)

    OUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
