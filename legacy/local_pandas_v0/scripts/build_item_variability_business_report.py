#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Optional

import pandas as pd


RAW_REQUIRED_COLUMNS = [
    "source_file",
    "source_sheet",
    "source_row_index",
    "source_table_header_row",
    "project_ean",
    "solicitation_no",
    "letting_date_raw",
    "location_name_raw",
    "project_name_raw",
    "bid_schedule_name",
    "bid_schedule_type",
    "bid_schedule_code",
    "line_no",
    "item_description_raw",
    "quantity_raw",
    "unit_code_raw",
    "unit_price_raw",
    "total_price_raw",
    "bidder_name_raw",
    "is_totals_row",
    "totals_row_label",
    "schedule_total_raw",
]

ISSUE_TOKENS = ["#REF!", "UNKNOWN", "N/A", "TBD", "???"]


def _to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1"])


def _parse_number(series: pd.Series) -> pd.Series:
    s = series.astype(str).str.strip()
    s = s.str.replace("$", "", regex=False).str.replace(",", "", regex=False)
    neg = s.str.startswith("(") & s.str.endswith(")")
    s = s.str.replace("(", "", regex=False).str.replace(")", "", regex=False)
    out = pd.to_numeric(s, errors="coerce")
    out[neg] = -out[neg]
    return out


def _clean_space(s: pd.Series) -> pd.Series:
    return s.astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def _extract_raw_spec_token(desc: pd.Series) -> pd.Series:
    s = _clean_space(desc).str.upper()
    sec = s.str.extract(r"SECTIONS?\s*([0-9]{4,6})", expand=False)
    item = s.str.extract(r"ITEM\s*([A-Z]{1,2}\s*-\s*\d{2,6})", expand=False)
    item = item.str.replace(r"\s*-\s*", "-", regex=True)
    out = sec.fillna(item).fillna("UNCLASSIFIED")
    out = out.astype(str).str.strip()
    out = out.where(out != "", "UNCLASSIFIED")
    return out


def _raw_variability_severity(distinct_count: pd.Series, ratio: pd.Series, unclassified_like: pd.Series) -> pd.Series:
    red = (distinct_count >= 20) | (ratio >= 0.23) | unclassified_like
    amber = ((distinct_count >= 8) & (distinct_count <= 19)) | ((ratio >= 0.13) & (ratio < 0.23))
    return pd.Series(pd.NA, index=distinct_count.index).mask(red, "RED").mask(~red & amber, "AMBER").fillna("GREEN")


def _rate_severity(rate: float, red: float, amber: float) -> str:
    if rate >= red:
        return "RED"
    if rate >= amber:
        return "AMBER"
    return "GREEN"


def _build_exec_summary(line: pd.DataFrame, spec_summary: pd.DataFrame) -> pd.DataFrame:
    top_specs = spec_summary.sort_values(["severity_rank", "row_count", "raw_variability_ratio"], ascending=[False, False, False]).head(5)
    top_desc = line["item_description_raw"].value_counts().head(5)

    rows = [
        ("rows_analyzed", len(line)),
        ("distinct_projects", line["project_ean"].nunique()),
        ("distinct_schedules", line[["project_ean", "bid_schedule_type", "bid_schedule_code"]].drop_duplicates().shape[0]),
        ("distinct_bidders_raw", line["bidder_name_raw"].nunique()),
        ("distinct_raw_item_descriptions", line["item_description_raw"].nunique()),
        ("pct_missing_unit_price_raw", round(line["unit_price_num"].isna().mean() * 100, 2)),
        ("pct_missing_total_price_raw", round(line["total_price_num"].isna().mean() * 100, 2)),
        (
            "pct_unclassified_like_raw_specs",
            round((line["raw_spec_token"].eq("UNCLASSIFIED")).mean() * 100, 2),
        ),
    ]

    for i, (_, r) in enumerate(top_specs.iterrows(), start=1):
        rows.append((f"top_unstable_spec_{i}", f"{r['raw_spec_token']} | rows={int(r['row_count'])} | distinct={int(r['distinct_raw_desc_count'])}"))

    for i, (label, cnt) in enumerate(top_desc.items(), start=1):
        rows.append((f"top_raw_description_{i}", f"{label} | count={int(cnt)}"))

    return pd.DataFrame(rows, columns=["metric", "value"])


def _build_raw_variability_overview(line: pd.DataFrame) -> pd.DataFrame:
    chunks = []

    for dim_col, dim_name in [
        ("project_ean", "project"),
        ("bid_schedule_type", "bid_schedule_type"),
        ("raw_spec_token", "raw_spec_token"),
    ]:
        g = (
            line.groupby(dim_col, dropna=False)
            .agg(row_count=("item_description_raw", "size"), distinct_raw_desc_count=("item_description_raw", "nunique"))
            .reset_index()
            .rename(columns={dim_col: "dimension_value"})
        )
        g["dimension_type"] = dim_name
        g["raw_variability_ratio"] = (g["distinct_raw_desc_count"] / g["row_count"]).round(4)
        g["severity_band"] = _raw_variability_severity(
            g["distinct_raw_desc_count"],
            g["raw_variability_ratio"],
            g["dimension_value"].astype(str).eq("UNCLASSIFIED"),
        )
        g["severity_rank"] = g["severity_band"].map({"GREEN": 1, "AMBER": 2, "RED": 3}).fillna(0)
        chunks.append(g)

    out = pd.concat(chunks, ignore_index=True)
    out = out[["dimension_type", "dimension_value", "row_count", "distinct_raw_desc_count", "raw_variability_ratio", "severity_band", "severity_rank"]]
    return out.sort_values(["severity_rank", "row_count", "dimension_type", "dimension_value"], ascending=[False, False, True, True], kind="stable").reset_index(drop=True)


def _build_spec_variability(line: pd.DataFrame) -> pd.DataFrame:
    g = (
        line.groupby("raw_spec_token", dropna=False)
        .agg(
            row_count=("item_description_raw", "size"),
            project_count=("project_ean", "nunique"),
            bidder_count=("bidder_name_raw", "nunique"),
            distinct_raw_desc_count=("item_description_raw", "nunique"),
        )
        .reset_index()
    )
    g["raw_variability_ratio"] = (g["distinct_raw_desc_count"] / g["row_count"]).round(4)
    g["unclassified_like_flag"] = g["raw_spec_token"].eq("UNCLASSIFIED") & (g["row_count"] >= 10)
    g["severity_band"] = _raw_variability_severity(g["distinct_raw_desc_count"], g["raw_variability_ratio"], g["unclassified_like_flag"])
    g["severity_rank"] = g["severity_band"].map({"GREEN": 1, "AMBER": 2, "RED": 3}).fillna(0)

    top_desc = (
        line.groupby(["raw_spec_token", "item_description_raw"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["raw_spec_token", "n", "item_description_raw"], ascending=[True, False, True], kind="stable")
    )
    top_desc = top_desc.groupby("raw_spec_token", dropna=False).head(10)
    top_desc = (
        top_desc.groupby("raw_spec_token", dropna=False)
        .apply(lambda d: "; ".join([f"{r.item_description_raw} ({int(r.n)})" for r in d.itertuples(index=False)]))
        .reset_index(name="top_raw_descriptions")
    )

    g = g.merge(top_desc, on="raw_spec_token", how="left")
    return g.sort_values(["severity_rank", "row_count", "raw_variability_ratio", "raw_spec_token"], ascending=[False, False, False, True], kind="stable").reset_index(drop=True)


def _build_quality_issues(line: pd.DataFrame) -> pd.DataFrame:
    issues = []
    total = len(line)

    def add_issue(name: str, mask: pd.Series, definition: str, red: float, amber: float):
        cnt = int(mask.sum())
        pct = (cnt / total * 100) if total else 0.0
        issues.append(
            {
                "issue_type": name,
                "issue_count": cnt,
                "pct_rows": round(pct, 2),
                "severity_band": _rate_severity(pct, red, amber),
                "definition": definition,
            }
        )

    add_issue("missing_unit_price_raw", line["unit_price_num"].isna(), "unit_price_raw is blank/non-numeric", red=10.0, amber=5.0)
    add_issue("missing_total_price_raw", line["total_price_num"].isna(), "total_price_raw is blank/non-numeric", red=5.0, amber=2.0)

    bad_token_mask = line["item_description_raw"].astype(str).str.upper().apply(lambda s: any(tok in s for tok in ISSUE_TOKENS))
    add_issue("malformed_placeholder_text", bad_token_mask, "item_description_raw contains placeholder-like tokens", red=2.0, amber=0.5)

    nonstd_unit_mask = ~line["unit_code_raw"].astype(str).str.upper().str.fullmatch(r"[A-Z0-9\-\./ ]+")
    add_issue("nonstandard_unit_code_raw", nonstd_unit_mask, "unit_code_raw contains unusual symbols/patterns", red=1.0, amber=0.2)

    unclassified_mask = line["raw_spec_token"].eq("UNCLASSIFIED")
    add_issue("unclassified_like_spec", unclassified_mask, "raw spec token not identifiable from raw description", red=20.0, amber=10.0)

    return pd.DataFrame(issues).sort_values(["severity_band", "issue_count"], ascending=[False, False], kind="stable").reset_index(drop=True)


def _build_project_variability(line: pd.DataFrame) -> pd.DataFrame:
    g = (
        line.groupby("project_ean", dropna=False)
        .agg(
            row_count=("item_description_raw", "size"),
            distinct_raw_desc_count=("item_description_raw", "nunique"),
            distinct_raw_spec_tokens=("raw_spec_token", "nunique"),
            missing_unit_price_count=("unit_price_num", lambda s: int(s.isna().sum())),
            missing_total_price_count=("total_price_num", lambda s: int(s.isna().sum())),
        )
        .reset_index()
    )
    g["raw_variability_ratio"] = (g["distinct_raw_desc_count"] / g["row_count"]).round(4)
    g["severity_band"] = _raw_variability_severity(
        g["distinct_raw_desc_count"], g["raw_variability_ratio"], pd.Series(False, index=g.index)
    )
    return g.sort_values(["raw_variability_ratio", "row_count", "project_ean"], ascending=[False, False, True], kind="stable").reset_index(drop=True)


def _build_schedule_comparison(line: pd.DataFrame) -> pd.DataFrame:
    g = (
        line.groupby("bid_schedule_type", dropna=False)
        .agg(
            row_count=("item_description_raw", "size"),
            distinct_raw_desc_count=("item_description_raw", "nunique"),
            missing_unit_price_count=("unit_price_num", lambda s: int(s.isna().sum())),
            missing_total_price_count=("total_price_num", lambda s: int(s.isna().sum())),
        )
        .reset_index()
    )
    g["raw_variability_ratio"] = (g["distinct_raw_desc_count"] / g["row_count"]).round(4)
    g["missing_unit_price_pct"] = (g["missing_unit_price_count"] / g["row_count"] * 100).round(2)
    g["missing_total_price_pct"] = (g["missing_total_price_count"] / g["row_count"] * 100).round(2)
    g["severity_band"] = _raw_variability_severity(
        g["distinct_raw_desc_count"], g["raw_variability_ratio"], pd.Series(False, index=g.index)
    )
    return g.sort_values(["row_count", "bid_schedule_type"], ascending=[False, True], kind="stable").reset_index(drop=True)


def _build_raw_vs_smart_clean(line_raw: pd.DataFrame, clean_csv: Optional[Path]) -> pd.DataFrame:
    if clean_csv is None or (not clean_csv.exists()):
        return pd.DataFrame(
            [{
                "note": "Clean comparison source not provided/found. This tab is intentionally optional and non-baseline.",
                "comparison_enabled": False,
            }]
        )

    clean = pd.read_csv(clean_csv, keep_default_na=False)
    clean = clean[~_to_bool(clean.get("is_totals_row", pd.Series(False, index=clean.index)))].copy()
    clean = clean[clean["line_no"].astype(str).str.strip() != ""]

    join_cols = ["source_file", "source_sheet", "source_row_index", "line_no", "bidder_name_raw"]
    right_cols = join_cols + ["pay_item_description", "specification"]
    merged = line_raw.merge(clean[right_cols], on=join_cols, how="left")

    merged["raw_desc_key"] = _clean_space(merged["item_description_raw"])
    merged["clean_desc_key"] = _clean_space(merged["pay_item_description"]).where(_clean_space(merged["pay_item_description"]) != "", "<EMPTY_CLEAN>")
    merged["specification"] = _clean_space(merged["specification"]).where(_clean_space(merged["specification"]) != "", "UNCLASSIFIED")

    g = (
        merged.groupby(["specification", "clean_desc_key"], dropna=False)
        .agg(
            row_count=("raw_desc_key", "size"),
            raw_variants_collapsed=("raw_desc_key", "nunique"),
            representative_raw=("item_description_raw", "first"),
            sample_project=("project_ean", "first"),
        )
        .reset_index()
        .rename(columns={"clean_desc_key": "smart_clean_description"})
    )
    return g.sort_values(["raw_variants_collapsed", "row_count", "specification"], ascending=[False, False, True], kind="stable").reset_index(drop=True)


def _build_top_actions(spec_summary: pd.DataFrame, line: pd.DataFrame) -> pd.DataFrame:
    quality_by_spec = (
        line.groupby("raw_spec_token", dropna=False)
        .agg(
            row_count=("item_description_raw", "size"),
            missing_unit_price_pct=("unit_price_num", lambda s: round(s.isna().mean() * 100, 2)),
            missing_total_price_pct=("total_price_num", lambda s: round(s.isna().mean() * 100, 2)),
        )
        .reset_index()
    )

    out = spec_summary.merge(quality_by_spec, on="raw_spec_token", how="left", suffixes=("", "_q"))
    out["impact_score"] = (
        out["row_count"]
        * (out["raw_variability_ratio"].fillna(0) + out["missing_unit_price_pct"].fillna(0) / 100 + out["missing_total_price_pct"].fillna(0) / 100)
    ).round(2)
    out["recommended_action"] = "Standardize recurring raw descriptions"
    out.loc[out["raw_spec_token"].eq("UNCLASSIFIED"), "recommended_action"] = "Define/assign spec token rules"
    out.loc[out["missing_unit_price_pct"].fillna(0) >= 10, "recommended_action"] = "Investigate missing unit prices in source sheets"
    out["owner"] = ""
    out["status"] = ""

    keep = [
        "raw_spec_token",
        "row_count",
        "distinct_raw_desc_count",
        "raw_variability_ratio",
        "missing_unit_price_pct",
        "missing_total_price_pct",
        "severity_band",
        "impact_score",
        "recommended_action",
        "owner",
        "status",
    ]
    return out[keep].sort_values(["impact_score", "row_count"], ascending=[False, False], kind="stable").reset_index(drop=True)


def _build_rulebook() -> pd.DataFrame:
    rows = [
        ("source_contract", "baseline_source", "compiled_excel_itemized_raw_snapshot.csv"),
        ("source_contract", "comparison_source", "compiled_excel_itemized_clean.csv (optional, comparison-only)"),
        ("exclusion", "excluded_metric", "parse_confidence"),
        ("threshold_variability", "red", "distinct_raw_desc_count >= 20 OR raw_variability_ratio >= 0.23 OR UNCLASSIFIED with row_count >= 10"),
        ("threshold_variability", "amber", "distinct_raw_desc_count 8-19 OR raw_variability_ratio 0.13-0.229"),
        ("threshold_quality_missing_unit_price", "red", ">= 10%"),
        ("threshold_quality_missing_unit_price", "amber", "5% to <10%"),
        ("threshold_quality_missing_total_price", "red", ">= 5%"),
        ("threshold_quality_missing_total_price", "amber", "2% to <5%"),
    ]
    return pd.DataFrame(rows, columns=["category", "name", "value"])


def build_report(raw_snapshot_csv: Path, clean_csv: Optional[Path], out_xlsx: Path, out_dir: Path, prefix: str) -> None:
    raw = pd.read_csv(raw_snapshot_csv, keep_default_na=False)
    missing = [c for c in RAW_REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise SystemExit(f"Raw snapshot missing required columns: {missing}")

    line = raw[~_to_bool(raw["is_totals_row"])].copy()
    line = line[line["line_no"].astype(str).str.strip() != ""].copy()

    line["item_description_raw"] = _clean_space(line["item_description_raw"])
    line["unit_price_num"] = _parse_number(line["unit_price_raw"])
    line["total_price_num"] = _parse_number(line["total_price_raw"])
    line["raw_spec_token"] = _extract_raw_spec_token(line["item_description_raw"])

    spec_summary = _build_spec_variability(line)
    exec_summary = _build_exec_summary(line, spec_summary)
    overview = _build_raw_variability_overview(line)
    quality = _build_quality_issues(line)
    project_var = _build_project_variability(line)
    schedule_cmp = _build_schedule_comparison(line)
    raw_vs_clean = _build_raw_vs_smart_clean(line, clean_csv)
    top_actions = _build_top_actions(spec_summary, line)
    rulebook = _build_rulebook()

    out_dir.mkdir(parents=True, exist_ok=True)

    exec_csv = out_dir / f"{prefix}_exec_summary.csv"
    spec_csv = out_dir / f"{prefix}_spec_summary.csv"
    comp_csv = out_dir / f"{prefix}_raw_vs_clean.csv"
    qual_csv = out_dir / f"{prefix}_quality_issues.csv"
    rule_csv = out_dir / f"{prefix}_rulebook.csv"

    exec_summary.to_csv(exec_csv, index=False)
    spec_summary.to_csv(spec_csv, index=False)
    raw_vs_clean.to_csv(comp_csv, index=False)
    quality.to_csv(qual_csv, index=False)
    rulebook.to_csv(rule_csv, index=False)

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        readme = pd.DataFrame(
            [
                ("Purpose", "Business-facing raw-first variability report."),
                ("Authoritative Baseline Source", str(raw_snapshot_csv)),
                ("Comparison Source (Optional)", str(clean_csv) if clean_csv else "Not provided"),
                ("Important Exclusions", "parse_confidence and parser-internal metrics are excluded."),
                ("Interpretation", "Baseline tabs use raw snapshot only; RAW_VS_SMART_CLEAN is comparison-only."),
            ],
            columns=["topic", "detail"],
        )
        readme.to_excel(writer, index=False, sheet_name="README")
        exec_summary.to_excel(writer, index=False, sheet_name="EXEC_SUMMARY")
        overview.to_excel(writer, index=False, sheet_name="RAW_VARIABILITY_OVERVIEW")
        spec_summary.to_excel(writer, index=False, sheet_name="RAW_SPEC_VARIABILITY")
        quality.to_excel(writer, index=False, sheet_name="QUALITY_ISSUES")
        project_var.to_excel(writer, index=False, sheet_name="PROJECT_VARIABILITY")
        schedule_cmp.to_excel(writer, index=False, sheet_name="SCHEDULE_COMPARISON")
        raw_vs_clean.to_excel(writer, index=False, sheet_name="RAW_VS_SMART_CLEAN")
        top_actions.to_excel(writer, index=False, sheet_name="TOP_ACTIONS")

        wb = writer.book
        red_fmt = wb.add_format({"bg_color": "#F4CCCC"})
        amber_fmt = wb.add_format({"bg_color": "#FCE5CD"})
        green_fmt = wb.add_format({"bg_color": "#D9EAD3"})

        for name in [
            "README",
            "EXEC_SUMMARY",
            "RAW_VARIABILITY_OVERVIEW",
            "RAW_SPEC_VARIABILITY",
            "QUALITY_ISSUES",
            "PROJECT_VARIABILITY",
            "SCHEDULE_COMPARISON",
            "RAW_VS_SMART_CLEAN",
            "TOP_ACTIONS",
        ]:
            ws = writer.sheets[name]
            ws.freeze_panes(1, 0)
            ws.set_column("A:Z", 28)
            ws.set_column("A:A", 36)

        sheet_cols = {
            "RAW_VARIABILITY_OVERVIEW": "F:F",
            "RAW_SPEC_VARIABILITY": "H:H",
            "QUALITY_ISSUES": "D:D",
            "PROJECT_VARIABILITY": "H:H",
            "SCHEDULE_COMPARISON": "G:G",
            "TOP_ACTIONS": "G:G",
        }
        for sheet, col in sheet_cols.items():
            ws = writer.sheets[sheet]
            rng = f"{col.split(':')[0]}2:{col.split(':')[0]}1048576"
            ws.conditional_format(rng, {"type": "text", "criteria": "containing", "value": "RED", "format": red_fmt})
            ws.conditional_format(rng, {"type": "text", "criteria": "containing", "value": "AMBER", "format": amber_fmt})
            ws.conditional_format(rng, {"type": "text", "criteria": "containing", "value": "GREEN", "format": green_fmt})

    print(f"Wrote {out_xlsx}")
    print(f"Wrote {exec_csv}")
    print(f"Wrote {spec_csv}")
    print(f"Wrote {comp_csv}")
    print(f"Wrote {qual_csv}")
    print(f"Wrote {rule_csv}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build raw-first business variability workbook and CSV artifacts.")
    parser.add_argument("--raw_snapshot_csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    parser.add_argument("--clean_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--out_xlsx", default="./reports/item_variability_business_report.xlsx")
    parser.add_argument("--out_dir", default="./reports")
    parser.add_argument("--prefix", default="item_variability")
    args = parser.parse_args()

    clean_path = Path(args.clean_csv) if str(args.clean_csv).strip() else None
    if clean_path is not None and not clean_path.exists():
        clean_path = None

    build_report(
        raw_snapshot_csv=Path(args.raw_snapshot_csv),
        clean_csv=clean_path,
        out_xlsx=Path(args.out_xlsx),
        out_dir=Path(args.out_dir),
        prefix=args.prefix,
    )


if __name__ == "__main__":
    main()
