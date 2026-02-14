#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re

import pandas as pd


def clean_ws(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_spec_code(text: str) -> str:
    s = str(text or "")

    m = re.search(r"\((?:Item|Section|Sections)\s*([^)]*)\)", s, flags=re.IGNORECASE)
    if m:
        inside = m.group(1)
        code = re.search(r"([A-Z]-?\d+(?:\.\d+)?|\d{4,6})", inside, flags=re.IGNORECASE)
        if code:
            return code.group(1).upper()

    m = re.search(r"Item\s*([A-Z]-?\d+(?:\.\d+)?)", s, flags=re.IGNORECASE)
    if m:
        return m.group(1).upper()

    m = re.search(r"Section\s*(\d{4,6})", s, flags=re.IGNORECASE)
    if m:
        return m.group(1)

    return ""


def clean_description(text: str, code: str) -> str:
    s = clean_ws(text)
    s = re.sub(r"\s*\((?:Item|Section|Sections)\s*[^)]*\)\s*$", "", s, flags=re.IGNORECASE)
    if code:
        s = re.sub(rf"\b(?:Item|Section|Sections)?\s*{re.escape(code)}\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\(\s*\)", "", s)
    s = clean_ws(s)
    return s


def build_detail_frame(compiled: pd.DataFrame) -> pd.DataFrame:
    c = compiled.copy()

    if "is_totals_row" in c.columns:
        c = c[~c["is_totals_row"].astype(str).str.lower().isin(["true", "1"])].copy()

    c["Project EAN"] = c.get("project_ean", "").astype(str)
    c["Item Sequence"] = c.get("item_no", c.get("line_no", "")).astype(str)
    c["Original Raw Text"] = c.get("item_description_raw", "").astype(str).map(clean_ws)

    c["standard_code"] = c["Original Raw Text"].apply(extract_spec_code)
    c.loc[c["standard_code"].astype(str).str.strip() == "", "standard_code"] = "UNCLASSIFIED"

    c["clean_description"] = c.apply(
        lambda r: clean_description(r["Original Raw Text"], "" if r["standard_code"] == "UNCLASSIFIED" else r["standard_code"]),
        axis=1,
    )

    unit = c.get("unit_code_norm", pd.Series("", index=c.index)).astype(str).str.upper().str.strip()
    raw_unit = c.get("unit_code_raw", pd.Series("", index=c.index)).astype(str).str.upper().str.strip()
    unit.loc[unit == ""] = raw_unit.loc[unit == ""]
    c["Unit"] = unit

    c["Unit Price"] = pd.to_numeric(c.get("unit_price", None), errors="coerce")

    return c[
        [
            "Project EAN",
            "Item Sequence",
            "standard_code",
            "clean_description",
            "Original Raw Text",
            "Unit",
            "Unit Price",
        ]
    ]


def build_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    # Deduplicate to count projects/items, not bidders.
    df_distinct = detail_df.drop_duplicates(subset=["Project EAN", "Item Sequence"]).copy()

    g = df_distinct.groupby("standard_code", dropna=False)
    summary = g.agg(
        **{
            "Project Count": ("Project EAN", "nunique"),
            "Distinct Descriptions": ("clean_description", lambda s: s.astype(str).str.strip().replace("", pd.NA).dropna().nunique()),
            "Sample Descriptions": ("clean_description", lambda s: " | ".join(list(dict.fromkeys([v for v in s.astype(str).tolist() if clean_ws(v)]))[:3])),
        }
    ).reset_index()

    summary = summary.rename(columns={"standard_code": "Spec Code"})
    summary["Variance Level"] = summary["Distinct Descriptions"].apply(lambda n: "HIGH" if int(n) > 1 else "LOW")
    summary.loc[summary["Spec Code"] == "UNCLASSIFIED", "Variance Level"] = "HIGH"
    summary = summary.sort_values(["Variance Level", "Distinct Descriptions", "Project Count", "Spec Code"], ascending=[True, False, False, True], kind="stable")
    return summary[["Spec Code", "Project Count", "Distinct Descriptions", "Sample Descriptions", "Variance Level"]]


def build_high_variance_details(detail_df: pd.DataFrame, summary_df: pd.DataFrame) -> pd.DataFrame:
    high_codes = set(summary_df.loc[summary_df["Variance Level"] == "HIGH", "Spec Code"].astype(str))
    if not high_codes:
        return pd.DataFrame(columns=["Spec Code", "Clean Description", "Original Raw Text", "Project EAN", "Avg Unit Price", "Reviewer Notes"])

    base = detail_df[detail_df["standard_code"].astype(str).isin(high_codes)].copy()

    # One row per distinct Spec Code + Clean Description for business review.
    grouped = (
        base.groupby(["standard_code", "clean_description"], dropna=False)
        .agg(
            **{
                "Original Raw Text": (
                    "Original Raw Text",
                    lambda s: " | ".join(list(dict.fromkeys([clean_ws(v) for v in s.astype(str).tolist() if clean_ws(v)]))[:3]),
                ),
                "Project EAN": (
                    "Project EAN",
                    lambda s: " | ".join(list(dict.fromkeys([clean_ws(v) for v in s.astype(str).tolist() if clean_ws(v)]))[:3]),
                ),
                "Avg Unit Price": ("Unit Price", "mean"),
            }
        )
        .reset_index()
    )

    grouped = grouped.rename(columns={"standard_code": "Spec Code", "clean_description": "Clean Description"})
    grouped["Reviewer Notes"] = ""
    grouped = grouped.sort_values(["Spec Code", "Clean Description"], kind="stable")
    return grouped[["Spec Code", "Clean Description", "Original Raw Text", "Project EAN", "Avg Unit Price", "Reviewer Notes"]]


def write_workbook(summary_df: pd.DataFrame, high_df: pd.DataFrame, out_xlsx: Path) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        wb = writer.book

        # Sheet 1: README_Instructions
        readme = wb.add_worksheet("README_Instructions")
        writer.sheets["README_Instructions"] = readme
        bold = wb.add_format({"bold": True})
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})

        readme.write("A1", "Workflow", bold)
        readme.write("A2", "1. Review Summary: Look for Variance Level = HIGH on the Summary tab.", wrap)
        readme.write("A3", "2. Drill Down: Go to HIGH_VARIANCE_DETAILS to view specific discrepancies.", wrap)
        readme.write("A4", "3. Action: Use the Reviewer Notes column to indicate if items should be split or renamed.", wrap)
        readme.set_column("A:A", 120)

        # Sheet 2: Similarity_Summary
        summary_df.to_excel(writer, index=False, sheet_name="Similarity_Summary")
        ws_sum = writer.sheets["Similarity_Summary"]
        nrows, ncols = summary_df.shape
        ws_sum.add_table(
            0,
            0,
            nrows,
            ncols - 1,
            {
                "name": "SimilaritySummaryTable",
                "style": "Table Style Medium 2",
                "columns": [{"header": c} for c in summary_df.columns],
            },
        )

        red = wb.add_format({"bg_color": "#F8CBAD", "font_color": "#9C0006"})
        var_col = summary_df.columns.get_loc("Variance Level")
        col_letter = chr(ord("A") + var_col)
        ws_sum.conditional_format(
            1,
            0,
            max(1, nrows),
            ncols - 1,
            {
                "type": "formula",
                "criteria": f'=${col_letter}2="HIGH"',
                "format": red,
            },
        )

        # Sheet 3: HIGH_VARIANCE_DETAILS
        high_df.to_excel(writer, index=False, sheet_name="HIGH_VARIANCE_DETAILS")
        ws_high = writer.sheets["HIGH_VARIANCE_DETAILS"]
        hnrows, hncols = high_df.shape
        ws_high.add_table(
            0,
            0,
            max(1, hnrows),
            hncols - 1,
            {
                "name": "HighVarianceDetailsTable",
                "style": "Table Style Medium 2",
                "columns": [{"header": c} for c in high_df.columns],
            },
        )

        yellow = wb.add_format({"bg_color": "#FFF2CC"})
        notes_col = high_df.columns.get_loc("Reviewer Notes")
        ws_high.set_column(notes_col, notes_col, 32, yellow)

        for ws_name, df in [("Similarity_Summary", summary_df), ("HIGH_VARIANCE_DETAILS", high_df)]:
            ws = writer.sheets[ws_name]
            for i, col in enumerate(df.columns):
                max_len = max(len(str(col)), int(df[col].astype(str).map(len).max()) if len(df) else 0)
                ws.set_column(i, i, min(max_len + 2, 90))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pay item similarity review workbook.")
    parser.add_argument("--input_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--output_xlsx", default="./reports/pay_item_similarity_review.xlsx")
    parser.add_argument("--output_csv", default="./reports/pay_item_similarity_review.csv")
    args = parser.parse_args()

    inp = Path(args.input_csv)
    if not inp.exists():
        raise SystemExit(f"Missing {inp}")

    compiled = pd.read_csv(inp, keep_default_na=False)
    detail = build_detail_frame(compiled)
    summary = build_summary(detail)
    high = build_high_variance_details(detail, summary)

    Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output_csv, index=False)
    write_workbook(summary, high, Path(args.output_xlsx))

    print(f"Wrote {args.output_csv} with {len(summary)} grouped rows")
    print(f"Wrote {args.output_xlsx}")


if __name__ == "__main__":
    main()
