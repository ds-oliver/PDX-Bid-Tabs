#!/usr/bin/env python3
from __future__ import annotations

import argparse
from difflib import SequenceMatcher
from pathlib import Path
import re
import sys

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
from bidtabs.parse_items import parse_description_components, parse_item_fields


def clean_ws(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _norm_for_match(value: str) -> str:
    text = clean_ws(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return clean_ws(text)


def extract_spec_code(raw: str) -> str:
    spec, _, _, _ = parse_description_components(raw)
    return spec


def extract_alt_spec_code(raw: str, primary: str | None = None) -> str:
    _, alt, _, _ = parse_description_components(raw)
    return alt


def load_spec_descriptions(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    df = pd.read_csv(path, keep_default_na=False)
    if not {"spec_code", "spec_description"}.issubset(df.columns):
        return {}
    out: dict[str, str] = {}
    for _, row in df.iterrows():
        code = clean_ws(row.get("spec_code", "")).upper()
        desc = clean_ws(row.get("spec_description", ""))
        if code and desc:
            out[code] = desc
    return out


def attach_spec_descriptions(df: pd.DataFrame, spec_map: dict[str, str], spec_col: str = "Specification") -> pd.Series:
    spec_series = df.get(spec_col, pd.Series("", index=df.index)).astype(str).str.upper().str.strip()
    mapped = spec_series.map(lambda s: spec_map.get(s, ""))
    mapped.loc[spec_series == "UNCLASSIFIED"] = "Unclassified / No parsed specification"
    return mapped.fillna("")


def build_fuzzy_candidate_index(detail_df: pd.DataFrame) -> pd.DataFrame:
    base = detail_df.copy()
    spec = base.get("Specification", pd.Series("", index=base.index)).astype(str).str.upper().str.strip()
    base = base[(spec != "") & (spec != "UNCLASSIFIED")].copy()
    if base.empty:
        return pd.DataFrame(columns=["Item", "candidate_text", "candidate_text_tokens"])

    base["Item"] = base.get("Item", "").astype(str).map(clean_ws)
    base["Pay Item Description"] = base.get("Pay Item Description", "").astype(str).map(clean_ws)
    base["Supplemental Description"] = base.get("Supplemental Description", "").astype(str).map(clean_ws)

    base["candidate_text"] = (
        base["Pay Item Description"].map(_norm_for_match)
        + " "
        + base["Supplemental Description"].map(_norm_for_match)
        + " "
        + base["Item"].map(_norm_for_match)
    ).map(clean_ws)
    base["candidate_text_tokens"] = base["candidate_text"].map(lambda s: " ".join(sorted(set(s.split()))))

    out = base[["Item", "candidate_text", "candidate_text_tokens"]].copy()
    out = out[out["Item"].astype(str).str.strip() != ""].drop_duplicates(subset=["Item"], keep="first").reset_index(drop=True)
    return out


def rank_matching_items(query_text: str, candidate_index: pd.DataFrame, top_n: int = 3) -> list[str]:
    if candidate_index.empty:
        return []

    q = _norm_for_match(query_text)
    if not q:
        return []
    q_tokens = " ".join(sorted(set(q.split())))

    scored: list[tuple[float, str]] = []
    for _, row in candidate_index.iterrows():
        item = clean_ws(row.get("Item", ""))
        if not item:
            continue
        c1 = str(row.get("candidate_text", ""))
        c2 = str(row.get("candidate_text_tokens", ""))
        s1 = SequenceMatcher(None, q, c1).ratio()
        s2 = SequenceMatcher(None, q_tokens, c2).ratio()
        scored.append((max(s1, s2), item))

    scored.sort(key=lambda x: (-x[0], x[1]))
    return [item for _, item in scored[:top_n]]


def build_detail_frame(compiled: pd.DataFrame) -> pd.DataFrame:
    c = compiled.copy()

    if "is_totals_row" in c.columns:
        c = c[~c["is_totals_row"].astype(str).str.lower().isin(["true", "1"])].copy()

    c["Project EAN"] = c.get("project_ean", "").astype(str)
    c["Item Sequence"] = c.get("item_no", c.get("line_no", "")).astype(str)
    c["Item Description Raw"] = c.get("item_description_raw", "").astype(str).map(clean_ws)

    parsed = c["Item Description Raw"].apply(parse_item_fields)
    parsed_df = pd.DataFrame(parsed.tolist(), index=c.index)
    c["Specification"] = parsed_df["spec_code_primary"]
    c["Alternate Specification"] = parsed_df["spec_code_alternates"]
    c["Pay Item Description"] = parsed_df["item"]
    c["Supplemental Description"] = parsed_df["supplemental_description"]
    c["Item"] = parsed_df["item_display"]
    c["Parse Type"] = parsed_df["parse_type"]

    unit = c.get("unit_code_norm", pd.Series("", index=c.index)).astype(str).str.upper().str.strip()
    raw_unit = c.get("unit_code_raw", pd.Series("", index=c.index)).astype(str).str.upper().str.strip()
    unit.loc[unit == ""] = raw_unit.loc[unit == ""]
    c["Unit"] = unit

    c["Unit Price"] = pd.to_numeric(c.get("unit_price", None), errors="coerce")

    return c[
        [
            "Project EAN",
            "Item Sequence",
            "Item Description Raw",
            "Item",
            "Specification",
            "Alternate Specification",
            "Pay Item Description",
            "Supplemental Description",
            "Unit",
            "Unit Price",
            "Parse Type",
        ]
    ]


def _sample_bullets(series: pd.Series, limit: int = 3) -> str:
    vals = list(dict.fromkeys([clean_ws(v) for v in series.astype(str).tolist() if clean_ws(v)]))[:limit]
    return "\n".join([f"- {v}" for v in vals])


def build_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    df_distinct = detail_df.drop_duplicates(subset=["Project EAN", "Item Sequence"]).copy()

    g = df_distinct.groupby("Specification", dropna=False)
    summary = g.agg(
        **{
            "Project Count": ("Project EAN", "nunique"),
            "Distinct Pay Item Descriptions": (
                "Pay Item Description",
                lambda s: s.astype(str).str.strip().replace("", pd.NA).dropna().nunique(),
            ),
            "Sample Pay Item Descriptions": (
                "Pay Item Description",
                lambda s: _sample_bullets(s, limit=3),
            ),
            "Distinct Supplemental Descriptions": (
                "Supplemental Description",
                lambda s: s.astype(str).str.strip().replace("", pd.NA).dropna().nunique(),
            ),
            "Sample Supplemental Descriptions": (
                "Supplemental Description",
                lambda s: _sample_bullets(s, limit=3),
            ),
        }
    ).reset_index()

    summary["Variance Level"] = summary["Distinct Pay Item Descriptions"].apply(lambda n: "HIGH" if int(n) > 1 else "LOW")
    summary.loc[summary["Specification"] == "UNCLASSIFIED", "Variance Level"] = "HIGH"
    summary = summary.sort_values(
        ["Variance Level", "Distinct Pay Item Descriptions", "Project Count", "Specification"],
        ascending=[True, False, False, True],
        kind="stable",
    )
    return summary[
        [
            "Specification",
            "Project Count",
            "Distinct Pay Item Descriptions",
            "Sample Pay Item Descriptions",
            "Distinct Supplemental Descriptions",
            "Sample Supplemental Descriptions",
            "Variance Level",
        ]
    ]


def build_high_variance_details(detail_df: pd.DataFrame, summary_df: pd.DataFrame) -> pd.DataFrame:
    high_specs = set(summary_df.loc[summary_df["Variance Level"] == "HIGH", "Specification"].astype(str))
    if not high_specs:
        return pd.DataFrame(
            columns=[
                "Item Description Raw",
                "Item",
                "Specification",
                "Alternate Specification",
                "Pay Item Description",
                "Supplemental Description",
                "Unit",
                "Avg Unit Price",
                "Example Project EANs",
                "Matching Spec 1",
                "Matching Spec 2",
                "Matching Spec 3",
                "Reviewer Notes",
            ]
        )

    base = detail_df[detail_df["Specification"].astype(str).isin(high_specs)].copy()

    grouped = (
        base.groupby(
            [
                "Item Description Raw",
                "Item",
                "Specification",
                "Alternate Specification",
                "Pay Item Description",
                "Supplemental Description",
                "Unit",
            ],
            dropna=False,
        )
        .agg(
            **{
                "Avg Unit Price": ("Unit Price", "mean"),
                "Example Project EANs": (
                    "Project EAN",
                    lambda s: _sample_bullets(s, limit=3),
                ),
            }
        )
        .reset_index()
    )

    candidates = build_fuzzy_candidate_index(detail_df)
    grouped["Matching Spec 1"] = ""
    grouped["Matching Spec 2"] = ""
    grouped["Matching Spec 3"] = ""
    unclassified_mask = grouped["Specification"].astype(str).str.upper().eq("UNCLASSIFIED")
    if unclassified_mask.any():
        matches = grouped.loc[unclassified_mask, "Item Description Raw"].map(lambda raw: rank_matching_items(str(raw), candidates, top_n=3))
        grouped.loc[unclassified_mask, "Matching Spec 1"] = matches.map(lambda x: x[0] if len(x) > 0 else "")
        grouped.loc[unclassified_mask, "Matching Spec 2"] = matches.map(lambda x: x[1] if len(x) > 1 else "")
        grouped.loc[unclassified_mask, "Matching Spec 3"] = matches.map(lambda x: x[2] if len(x) > 2 else "")

    grouped["Reviewer Notes"] = ""
    grouped = grouped.sort_values(["Specification", "Pay Item Description", "Supplemental Description", "Item Description Raw"], kind="stable")
    return grouped[
        [
            "Item Description Raw",
            "Item",
            "Specification",
            "Alternate Specification",
            "Pay Item Description",
            "Supplemental Description",
            "Unit",
            "Avg Unit Price",
            "Example Project EANs",
            "Matching Spec 1",
            "Matching Spec 2",
            "Matching Spec 3",
            "Reviewer Notes",
        ]
    ]


def write_workbook(summary_df: pd.DataFrame, high_df: pd.DataFrame, out_xlsx: Path) -> None:
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        wb = writer.book

        readme = wb.add_worksheet("README_Instructions")
        writer.sheets["README_Instructions"] = readme
        bold = wb.add_format({"bold": True})
        wrap = wb.add_format({"text_wrap": True, "valign": "top"})

        readme.write("A1", "Purpose", bold)
        readme.write(
            "A2",
            "This workbook supports business review of potentially overlapping pay item descriptions grouped by Specification.",
            wrap,
        )

        readme.write("A4", "Critical callouts", bold)
        readme.write("A5", "ODOT has a separate numeric Item ID; Port does not in this MVP. We use string Item = Specification + ' - ' + Pay Item Description.", wrap)
        readme.write("A6", "Alternative specs can appear in plural tokens (Sections ... and ...). Capture in Alternate Specification; Item is based on primary Specification.", wrap)

        readme.write("A8", "Workflow", bold)
        readme.write("A9", "1. Review Similarity_Summary and focus on Variance Level = HIGH.", wrap)
        readme.write("A10", "2. Go to HIGH_VARIANCE_DETAILS to inspect distinct Item/Specification/Pay Item Description combinations.", wrap)
        readme.write("A11", "3. Use Reviewer Notes to indicate whether rows should stay grouped, split, or be reassigned.", wrap)

        readme.write("A13", "Columns Guide (Similarity_Summary)", bold)
        readme.write("A14", "Specification: primary extracted code token (e.g., P-620, 012200); UNCLASSIFIED when not found.", wrap)
        readme.write("A15", "Spec Description: standardized section description lookup by specification code.", wrap)
        readme.write("A16", "Project Count: unique projects using the Specification (deduped by Project EAN + Item Sequence).", wrap)
        readme.write("A17", "Distinct Pay Item Descriptions: unique base descriptions under each Specification.", wrap)
        readme.write("A18", "Sample Pay Item Descriptions: up to 3 examples in bullet format.", wrap)
        readme.write("A19", "Variance Level: HIGH when Distinct Pay Item Descriptions > 1; UNCLASSIFIED forced HIGH.", wrap)

        readme.write("A21", "Columns Guide (HIGH_VARIANCE_DETAILS)", bold)
        readme.write("A22", "Item Description Raw: original text from bid tab sheet.", wrap)
        readme.write("A23", "Item: business-facing value (<Specification> - <Pay Item Description>).", wrap)
        readme.write("A24", "Specification: primary extracted specification code.", wrap)
        readme.write("A25", "Spec Description: standardized section description lookup by specification code.", wrap)
        readme.write("A26", "Alternate Specification: additional section code(s), if present.", wrap)
        readme.write("A27", "Pay Item Description: base item description.", wrap)
        readme.write("A28", "Supplemental Description: optional qualifier (size/range/type).", wrap)
        readme.write("A29", "Matching Spec 1/2/3: ranked fuzzy suggestions for UNCLASSIFIED rows.", wrap)
        readme.write("A30", "Reviewer Notes: business input field (yellow).", wrap)

        readme.set_column("A:A", 145)

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
            wrap_fmt = wb.add_format({"text_wrap": True, "valign": "top"})
            for i, col in enumerate(df.columns):
                max_len = max(len(str(col)), int(df[col].astype(str).map(len).max()) if len(df) else 0)
                ws.set_column(i, i, min(max_len + 2, 95), wrap_fmt)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pay item similarity review workbook.")
    parser.add_argument("--input_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--spec_catalog_csv", default="./config/spec_section_catalog.csv")
    parser.add_argument("--output_xlsx", default="./reports/pay_item_similarity_review.xlsx")
    parser.add_argument("--output_csv", default="./reports/pay_item_similarity_review.csv")
    args = parser.parse_args()

    inp = Path(args.input_csv)
    if not inp.exists():
        raise SystemExit(f"Missing {inp}")

    compiled = pd.read_csv(inp, keep_default_na=False)
    spec_map = load_spec_descriptions(Path(args.spec_catalog_csv))
    detail = build_detail_frame(compiled)
    summary = build_summary(detail)
    high = build_high_variance_details(detail, summary)
    summary.insert(1, "Spec Description", attach_spec_descriptions(summary, spec_map))
    spec_idx = high.columns.get_loc("Specification")
    high.insert(spec_idx + 1, "Spec Description", attach_spec_descriptions(high, spec_map))

    Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output_csv, index=False)
    write_workbook(summary, high, Path(args.output_xlsx))

    print(f"Wrote {args.output_csv} with {len(summary)} grouped rows")
    print(f"Wrote {args.output_xlsx}")


if __name__ == "__main__":
    main()
