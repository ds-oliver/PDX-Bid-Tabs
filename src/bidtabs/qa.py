from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd


@dataclass
class ParseIssue:
    source_file: str
    source_sheet: str
    issue_type: str
    details: str


def write_parse_summary(issues: Iterable[ParseIssue], out_path: Path) -> None:
    rows = [i.__dict__ for i in issues]
    df = pd.DataFrame(rows, columns=["source_file", "source_sheet", "issue_type", "details"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)


def arithmetic_checks(df: pd.DataFrame, tolerance: float = 0.02) -> pd.DataFrame:
    line_df = df[df["is_totals_row"] == False].copy()  # noqa: E712
    for col in ["quantity", "unit_price", "total_price"]:
        line_df[col] = pd.to_numeric(line_df[col], errors="coerce")

    line_df["total_price_calc"] = line_df["unit_price"] * line_df["quantity"]
    delta = (line_df["total_price"] - line_df["total_price_calc"]).abs()
    thresh = line_df["total_price"].abs().fillna(0).clip(lower=1) * tolerance
    line_df["arith_delta"] = delta
    line_df["arith_threshold"] = thresh
    line_df["arith_valid"] = (delta <= thresh) | line_df["total_price"].isna() | line_df["unit_price"].isna() | line_df["quantity"].isna()
    return line_df


def _build_totals_recon_detail(df: pd.DataFrame, tolerance_amount: float, tolerance_pct: float) -> pd.DataFrame:
    line_df = df[df["is_totals_row"] == False].copy()  # noqa: E712
    totals_df = df[df["is_totals_row"] == True].copy()  # noqa: E712

    for col in ["total_price", "total_price_calc", "unit_price", "schedule_total"]:
        if col in line_df.columns:
            line_df[col] = pd.to_numeric(line_df[col], errors="coerce")
        if col in totals_df.columns:
            totals_df[col] = pd.to_numeric(totals_df[col], errors="coerce")

    keys = [
        "source_file",
        "source_sheet",
        "project_ean",
        "solicitation_no",
        "letting_date",
        "bid_schedule_name",
        "bid_schedule_type",
        "bid_schedule_code",
        "bidder_name_raw",
        "bidder_name_canonical",
        "bidder_type",
    ]

    line_grp = (
        line_df.groupby(keys, dropna=False, as_index=False)
        .agg(
            sum_line_total_price=("total_price", "sum"),
            sum_line_total_price_calc=("total_price_calc", "sum"),
            line_item_count=("source_row_index", "count"),
            missing_total_price_count=("total_price", lambda s: int(s.isna().sum())),
            missing_unit_price_count=("unit_price", lambda s: int(s.isna().sum())),
        )
    )

    totals_grp = (
        totals_df.groupby(keys, dropna=False, as_index=False)
        .agg(schedule_total=("schedule_total", "max"))
    )

    merged = line_grp.merge(totals_grp, on=keys, how="outer")
    merged["delta_total_price"] = merged["sum_line_total_price"] - merged["schedule_total"]
    merged["delta_total_price_calc"] = merged["sum_line_total_price_calc"] - merged["schedule_total"]
    merged["delta_abs"] = merged["delta_total_price"].abs()
    merged["delta_pct"] = np.where(
        merged["schedule_total"].abs() > 0,
        merged["delta_abs"] / merged["schedule_total"].abs(),
        np.nan,
    )

    merged["tolerance_amount_used"] = float(tolerance_amount)
    merged["tolerance_pct_used"] = float(tolerance_pct)

    pct_thresh = merged["schedule_total"].abs().fillna(0) * float(tolerance_pct)
    merged["within_tolerance"] = (
        (merged["delta_abs"] <= float(tolerance_amount))
        | (merged["delta_abs"] <= pct_thresh)
    )

    def _root_cause(r):
        if pd.isna(r.get("schedule_total")):
            return "TOTALS_SCOPE"
        if (r.get("missing_total_price_count") or 0) > 0 or (r.get("missing_unit_price_count") or 0) > 0:
            return "PLACEHOLDERS"
        if (r.get("line_item_count") or 0) == 0:
            return "MISSED_LINES"
        d1 = abs(r.get("delta_total_price") or 0)
        d2 = abs(r.get("delta_total_price_calc") or 0)
        if d2 < d1:
            return "ROUNDING"
        if "|" in str(r.get("bid_schedule_name", "")):
            return "MULTI_TABLE"
        return "OTHER"

    merged["suspected_root_cause"] = merged.apply(_root_cause, axis=1)
    return merged


def totals_reconciliation(df: pd.DataFrame, tolerance_amount: float = 5.0, tolerance_pct: float = 0.02) -> pd.DataFrame:
    return _build_totals_recon_detail(df, tolerance_amount=tolerance_amount, tolerance_pct=tolerance_pct)


def totals_recon_exceptions(df: pd.DataFrame, tolerance_amount: float = 5.0, tolerance_pct: float = 0.02) -> pd.DataFrame:
    recon = _build_totals_recon_detail(df, tolerance_amount=tolerance_amount, tolerance_pct=tolerance_pct)
    failed = recon[~recon["within_tolerance"].fillna(False)].copy()
    out_cols = [
        "source_file",
        "source_sheet",
        "project_ean",
        "solicitation_no",
        "letting_date",
        "bid_schedule_type",
        "bid_schedule_code",
        "bidder_name_raw",
        "bidder_name_canonical",
        "bidder_type",
        "schedule_total",
        "sum_line_total_price",
        "sum_line_total_price_calc",
        "delta_total_price",
        "delta_total_price_calc",
        "delta_abs",
        "delta_pct",
        "line_item_count",
        "missing_total_price_count",
        "missing_unit_price_count",
        "tolerance_amount_used",
        "tolerance_pct_used",
        "suspected_root_cause",
    ]
    for c in out_cols:
        if c not in failed.columns:
            failed[c] = np.nan
    return failed[out_cols]


def enforce_canonical_key_uniqueness(df: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["source_file", "source_sheet", "source_row_index", "bidder_name_canonical", "is_totals_row"]
    dupes = df[df.duplicated(subset=key_cols, keep=False)].sort_values(key_cols)
    return dupes


def write_qa_reports(
    df: pd.DataFrame,
    report_dir: Path,
    tolerance: float = 0.02,
    tolerance_amount: float = 5.0,
    tolerance_pct: float = 0.02,
) -> Dict[str, pd.DataFrame]:
    report_dir.mkdir(parents=True, exist_ok=True)
    arithmetic = arithmetic_checks(df, tolerance=tolerance)
    arithmetic_out = arithmetic[
        [
            "source_file",
            "source_sheet",
            "source_row_index",
            "bidder_name_canonical",
            "quantity",
            "unit_price",
            "total_price",
            "total_price_calc",
            "arith_delta",
            "arith_threshold",
            "arith_valid",
        ]
    ]
    arithmetic_out.to_csv(report_dir / "qa_price_arithmetic.csv", index=False)

    recon = totals_reconciliation(df, tolerance_amount=tolerance_amount, tolerance_pct=tolerance_pct)
    recon.to_csv(report_dir / "qa_totals_recon.csv", index=False)

    recon_ex = totals_recon_exceptions(df, tolerance_amount=tolerance_amount, tolerance_pct=tolerance_pct)
    recon_ex.to_csv(report_dir / "qa_totals_recon_exceptions.csv", index=False)

    return {
        "qa_price_arithmetic": arithmetic_out,
        "qa_totals_recon": recon,
        "qa_totals_recon_exceptions": recon_ex,
    }
