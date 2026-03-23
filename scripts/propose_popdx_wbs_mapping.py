#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class WbsRule:
    rule_id: str
    pop_wbs_code: str
    wbs_description: str
    groups: tuple[str, ...] = ()
    subgroups: tuple[str, ...] = ()
    specs: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _canon_text(*parts: str) -> str:
    s = " ".join(str(p or "") for p in parts).upper()
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


def _match_rule(row: pd.Series, rule: WbsRule) -> bool:
    g = _norm(row.get("item_group", ""))
    sg = _norm(row.get("item_subgroup", ""))
    spec = _norm(row.get("specification", ""))
    text = f" {_canon_text(row.get('pay_item_description', ''), row.get('item_description_raw', ''), row.get('item', ''))} "

    if rule.groups and g not in rule.groups:
        return False
    if rule.subgroups and sg not in rule.subgroups:
        return False
    if rule.specs and spec not in rule.specs:
        return False
    if rule.keywords and not _contains_any(text, rule.keywords):
        return False
    return True


WBS_RULES: list[WbsRule] = [
    # Temporary / general conditions.
    WbsRule(
        "temp_security_access_control",
        "1.6.F10.281300",
        "Access Control",
        groups=("GENERAL_TEMPORARY",),
        keywords=(" SECURITY CONTROL ", " ACCESS CONTROL ", " MONITORING "),
    ),
    WbsRule(
        "temp_safety_controls",
        "1.7.Z10.013500",
        "Safety & Controls",
        groups=("GENERAL_TEMPORARY",),
        keywords=(" TRAFFIC CONTROL ", " ESCORT ", " SAFETY ", " CONTROL "),
    ),
    WbsRule(
        "temp_facilities",
        "1.7.Z10.015000",
        "Temporary Facilities",
        groups=("GENERAL_TEMPORARY",),
    ),
    # Airfield paving/marking (FAA P-items).
    WbsRule(
        "airfield_markings",
        "1.2.G40.321723",
        "Pavement Markings",
        groups=("ROADWORK_PAVING",),
        specs=("P-620",),
    ),
    WbsRule(
        "airfield_concrete_paving",
        "1.2.G40.321313",
        "Concrete Paving",
        groups=("ROADWORK_PAVING",),
        specs=("P-501",),
    ),
    WbsRule(
        "airfield_pavement_removal",
        "1.2.G40.321216",
        "Pavement Removal",
        groups=("ROADWORK_PAVING",),
        specs=("P-101",),
    ),
    WbsRule(
        "airfield_asphalt",
        "1.2.G40.321216",
        "Airfield Asphalt",
        groups=("ROADWORK_PAVING",),
        specs=("P-401", "P-403", "P-602", "P-603", "P-604", "P-605", "P-606", "P-608", "P-621", "P-626"),
    ),
    # Site earthwork / aggregate.
    WbsRule(
        "site_earthwork",
        "1.3.G20.311000",
        "Earthwork",
        groups=("ROADWORK_PAVING",),
        specs=("P-152", "P-153", "026100", "024113"),
    ),
    WbsRule(
        "site_aggregate_base",
        "1.3.G20.321000",
        "Aggregate Base",
        groups=("ROADWORK_PAVING",),
        specs=("P-154", "P-156", "P-209", "P-306"),
    ),
    WbsRule(
        "site_earthwork_keywords",
        "1.3.G20.311000",
        "Earthwork",
        groups=("ROADWORK_PAVING",),
        keywords=(" EXCAVATION ", " TRENCH ", " BACKFILL ", " UNSUITABLE ", " REMOVAL "),
    ),
    # Drainage / utilities.
    WbsRule(
        "storm_sewer_pipe",
        "1.4.G30.334000",
        "Storm Sewer",
        groups=("PIPING_DRAINAGE",),
        specs=("D-701", "D-705", "334100"),
    ),
    WbsRule(
        "manholes_structures",
        "1.4.G30.334213",
        "Manholes",
        groups=("PIPING_DRAINAGE",),
        specs=("D-751", "D-752"),
    ),
    WbsRule(
        "pump_stations",
        "1.4.G30.334600",
        "Pump Stations",
        groups=("PIPING_DRAINAGE",),
        specs=("334213",),
    ),
    WbsRule(
        "drainage_misc",
        "1.4.G30.334000",
        "Storm Sewer",
        groups=("PIPING_DRAINAGE",),
    ),
    # Electrical and communications.
    WbsRule(
        "airfield_signage",
        "1.5.D50.344302",
        "Airfield Signage",
        groups=("ELECTRICAL",),
        specs=("344302",),
    ),
    WbsRule(
        "airfield_lighting",
        "1.5.D50.344300",
        "Airfield Lighting",
        groups=("ELECTRICAL",),
        specs=("344300", "344301"),
    ),
    WbsRule(
        "electrical_grounding",
        "1.5.D50.260526",
        "Grounding",
        groups=("ELECTRICAL",),
        specs=("260526",),
    ),
    WbsRule(
        "electrical_conductors_l108",
        "1.5.D50.260519",
        "Conductors",
        groups=("ELECTRICAL",),
        specs=("L-108",),
    ),
    WbsRule(
        "electrical_raceways_l110",
        "1.5.D50.260533",
        "Raceways",
        groups=("ELECTRICAL",),
        specs=("L-110",),
    ),
    WbsRule(
        "electrical_comms",
        "1.5.D50.271000",
        "Communications",
        groups=("ELECTRICAL",),
        specs=("271000", "270553", "282300"),
    ),
    WbsRule(
        "electrical_distribution",
        "1.5.D50.260500",
        "Electrical Distribution",
        groups=("ELECTRICAL",),
    ),
    # Security / special systems.
    WbsRule(
        "security_special_systems",
        "1.6.F10.281300",
        "Access Control",
        groups=("SITEWORK_MISC",),
        keywords=(" SECURITY ", " SURVEILLANCE ", " ACCESS "),
    ),
    # Landscaping / environmental.
    WbsRule(
        "landscape_seeding",
        "1.3.G20.329219",
        "Seeding",
        groups=("LANDSCAPE_ENVIRONMENTAL",),
        specs=("T-901",),
    ),
    WbsRule(
        "landscape_topsoil",
        "1.3.G20.329113",
        "Topsoiling",
        groups=("LANDSCAPE_ENVIRONMENTAL",),
        specs=("T-905",),
    ),
    WbsRule(
        "landscape_maintenance",
        "1.3.G20.329200",
        "Landscape Maintenance",
        groups=("LANDSCAPE_ENVIRONMENTAL",),
        keywords=(" MAINTENANCE ",),
    ),
    WbsRule(
        "landscape_erosion_control",
        "1.3.G20.313200",
        "Erosion Control",
        groups=("LANDSCAPE_ENVIRONMENTAL",),
        keywords=(" EROSION ", " SEDIMENT ", " SILT ", " WATTLE ", " INLET PROTECTION "),
    ),
    WbsRule(
        "landscape_default",
        "1.3.G20.329200",
        "Landscape Maintenance",
        groups=("LANDSCAPE_ENVIRONMENTAL",),
    ),
]


def assign_wbs(row: pd.Series) -> tuple[str, str, str]:
    for rule in WBS_RULES:
        if _match_rule(row, rule):
            return rule.pop_wbs_code, rule.wbs_description, rule.rule_id
    return "", "REVIEW_NEEDED", "fallback_review"


def _item_label(row: pd.Series) -> str:
    desc = str(row.get("display_desc", "")).strip()
    if not desc:
        desc = str(row.get("pay_item_description", "")).strip() or str(row.get("item_description_raw", "")).strip()
    spec = _norm(row.get("specification", ""))
    if spec and spec != "UNCLASSIFIED":
        suffix = f"(Section {spec})" if re.match(r"^\d{6}$", spec) else f"(Item {spec})"
        return f"{desc} {suffix}".strip()
    return desc


def build_outputs(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out = df.copy()
    assigned = out.apply(assign_wbs, axis=1, result_type="expand")
    assigned.columns = ["pop_wbs_code", "wbs_description", "wbs_rule_id"]
    out = pd.concat([out, assigned], axis=1)

    # Canonicalize item text so obvious punctuation/spacing variants collapse in rollups.
    out["base_desc"] = out["pay_item_description"].astype(str).str.strip()
    out.loc[out["base_desc"] == "", "base_desc"] = out["item_description_raw"].astype(str).str.strip()
    out["canon_key"] = out["specification"].astype(str).str.upper().str.strip() + "|" + out["base_desc"].map(_canon_text)
    display = (
        out.groupby(["canon_key", "base_desc"], dropna=False)
        .size()
        .reset_index(name="n")
        .sort_values(["canon_key", "n", "base_desc"], ascending=[True, False, True], kind="stable")
        .drop_duplicates(subset=["canon_key"], keep="first")[["canon_key", "base_desc"]]
        .rename(columns={"base_desc": "display_desc"})
    )
    out = out.merge(display, on="canon_key", how="left")
    out["item_label"] = out.apply(_item_label, axis=1)

    detail_cols = [
        "item_id",
        "project_id",
        "line_no",
        "item_group",
        "item_subgroup",
        "specification",
        "pay_item_description",
        "item_description_raw",
        "item_label",
        "pop_wbs_code",
        "wbs_description",
        "wbs_rule_id",
    ]
    detail = out[detail_cols].copy()

    rollup = (
        detail.groupby(
            ["item_group", "item_subgroup", "item_label", "pop_wbs_code", "wbs_description", "wbs_rule_id"],
            dropna=False,
        )
        .size()
        .reset_index(name="count_of_item_description_raw")
        .sort_values(["item_group", "item_subgroup", "count_of_item_description_raw", "item_label"], ascending=[True, True, False, True], kind="stable")
    )

    summary = (
        detail.groupby(["item_group", "item_subgroup", "pop_wbs_code", "wbs_description"], dropna=False)
        .size()
        .reset_index(name="item_rows")
        .sort_values(["item_rows", "item_group"], ascending=[False, True], kind="stable")
    )
    summary["pct_rows"] = (summary["item_rows"] / len(detail) * 100).round(2)
    return detail, rollup, summary


def build_pivot_like(rollup: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for item_group in rollup["item_group"].drop_duplicates():
        g = rollup[rollup["item_group"] == item_group]
        rows.append({"Row Labels": item_group, "Count of item_description_raw": int(g["count_of_item_description_raw"].sum())})
        for item_subgroup in g["item_subgroup"].drop_duplicates():
            s = g[g["item_subgroup"] == item_subgroup]
            rows.append({"Row Labels": item_subgroup, "Count of item_description_raw": int(s["count_of_item_description_raw"].sum())})
            for _, r in s.sort_values(["count_of_item_description_raw", "item_label"], ascending=[False, True], kind="stable").iterrows():
                rows.append({"Row Labels": r["item_label"], "Count of item_description_raw": int(r["count_of_item_description_raw"])})
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose PoPDX WBS mapping from grouped items.")
    parser.add_argument("--grouping_csv", default="./reports/item_grouping_proposal.csv")
    parser.add_argument("--out_xlsx", default="./reports/item_wbs_mapping.xlsx")
    parser.add_argument("--out_dir", default="./reports")
    args = parser.parse_args()

    grouping = pd.read_csv(Path(args.grouping_csv), keep_default_na=False)
    detail, rollup, summary = build_outputs(grouping)
    pivot_like = build_pivot_like(rollup)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_xlsx = Path(args.out_xlsx)

    detail.to_csv(out_dir / "item_wbs_mapping_detail.csv", index=False)
    rollup.to_csv(out_dir / "item_wbs_mapping_rollup.csv", index=False)
    summary.to_csv(out_dir / "item_wbs_mapping_summary.csv", index=False)
    pivot_like.to_csv(out_dir / "item_wbs_mapping_pivot_like.csv", index=False)

    rulebook = pd.DataFrame(
        [
            {
                "rule_order": i + 1,
                "rule_id": r.rule_id,
                "pop_wbs_code": r.pop_wbs_code,
                "wbs_description": r.wbs_description,
                "groups": "|".join(r.groups),
                "subgroups": "|".join(r.subgroups),
                "specs": "|".join(r.specs),
                "keywords": "|".join(r.keywords),
            }
            for i, r in enumerate(WBS_RULES)
        ]
    )
    rulebook.to_csv(out_dir / "item_wbs_mapping_rulebook.csv", index=False)

    with pd.ExcelWriter(out_xlsx, engine="xlsxwriter") as writer:
        pivot_like.to_excel(writer, index=False, sheet_name="Pivot_Like")
        rollup.to_excel(writer, index=False, sheet_name="WBS_Rollup")
        summary.to_excel(writer, index=False, sheet_name="WBS_Summary")
        rulebook.to_excel(writer, index=False, sheet_name="Rulebook")
        detail.to_excel(writer, index=False, sheet_name="Detail")

        wb = writer.book
        for name, width in [
            ("Pivot_Like", (110, 28)),
            ("WBS_Rollup", (56, 22)),
            ("WBS_Summary", (36, 20)),
            ("Rulebook", (26, 46)),
            ("Detail", (38, 22)),
        ]:
            ws = writer.sheets[name]
            ws.freeze_panes(1, 0)
            ws.set_column("A:A", width[0])
            ws.set_column("B:Z", width[1])
            wrap = wb.add_format({"text_wrap": True, "valign": "top"})
            ws.set_column("A:Z", None, wrap)

    print(f"Wrote {out_xlsx}")
    print(f"Wrote {out_dir / 'item_wbs_mapping_pivot_like.csv'} ({len(pivot_like)} rows)")
    print(f"Wrote {out_dir / 'item_wbs_mapping_detail.csv'} ({len(detail)} rows)")


if __name__ == "__main__":
    main()
