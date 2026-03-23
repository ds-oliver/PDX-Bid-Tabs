#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import pandas as pd


@dataclass(frozen=True)
class Rule:
    rule_id: str
    item_group: str
    item_subgroup: str
    kind: str
    values: tuple[str, ...]


def _norm(s: str) -> str:
    return str(s or "").strip().upper()


def _text_blob(specification: str, pay_item_description: str, item_description_raw: str) -> str:
    parts = [specification, pay_item_description, item_description_raw]
    joined = " ".join(str(p or "") for p in parts).upper()
    # Keep matching robust to punctuation and odd workbook spacing.
    joined = re.sub(r"[^A-Z0-9]+", " ", joined)
    return re.sub(r"\s+", " ", joined).strip()


def _contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(n in text for n in needles)


SPEC_RULES: list[Rule] = [
    Rule("spec_airfield_lighting", "ELECTRICAL", "AIRFIELD_LIGHTING", "spec_in", ("L-108", "L-110", "344300", "344301")),
    Rule("spec_airfield_signage", "ELECTRICAL", "AIRFIELD_SIGNAGE", "spec_in", ("344302",)),
    Rule(
        "spec_power_distribution",
        "ELECTRICAL",
        "POWER_DISTRIBUTION",
        "spec_in",
        ("260500", "260526", "260543", "260553", "262200", "262400", "265000", "265623"),
    ),
    Rule("spec_telecom_it", "ELECTRICAL", "TELECOM_IT", "spec_in", ("270553", "271000", "282300")),
    Rule("spec_ev_charging", "ELECTRICAL", "EV_CHARGING", "spec_in", ("263343",)),
    Rule(
        "spec_drainage_structures",
        "PIPING_DRAINAGE",
        "DRAINAGE_STRUCTURES",
        "spec_in",
        ("D-701", "D-705", "D-751", "D-752", "312300"),
    ),
    Rule(
        "spec_piping_utility",
        "PIPING_DRAINAGE",
        "PIPING_UTILITY",
        "spec_in",
        ("330516", "331116", "334100", "334213"),
    ),
    Rule(
        "spec_paving_earthwork",
        "ROADWORK_PAVING",
        "PAVING_EARTHWORK",
        "spec_in",
        (
            "P-101",
            "P-152",
            "P-153",
            "P-154",
            "P-156",
            "P-209",
            "P-306",
            "P-401",
            "P-403",
            "P-501",
            "P-602",
            "P-603",
            "P-604",
            "P-605",
            "P-606",
            "P-608",
            "P-610",
            "P-620",
            "P-621",
            "P-626",
            "320117",
            "320118",
            "321613",
        ),
    ),
    Rule("spec_temp_traffic", "GENERAL_TEMPORARY", "TEMP_TRAFFIC_MOBILIZATION", "spec_in", ("012200", "015713", "C-102", "C-105")),
    Rule("spec_demo_remediation", "DEMOLITION_REMEDIATION", "DEMOLITION_REMEDIATION", "spec_in", ("024113", "026100")),
    Rule("spec_landscape", "LANDSCAPE_ENVIRONMENTAL", "LANDSCAPING_REVEGETATION", "spec_in", ("T-901", "T-905", "328400", "329300", "354000")),
    Rule("spec_site_safety", "SITEWORK_MISC", "FENCING_GUARDRAIL_BOLLARDS", "spec_in", ("323113", "347113", "347115", "111100")),
]


KEYWORD_RULES: list[Rule] = [
    Rule("kw_airfield_signage", "ELECTRICAL", "AIRFIELD_SIGNAGE", "kw_any", (" SIGNAGE ", " SIGN ")),
    Rule(
        "kw_airfield_lighting",
        "ELECTRICAL",
        "AIRFIELD_LIGHTING",
        "kw_any",
        (" LIGHT ", " LIGHTING ", " TRANSFORMER ", " CONDUIT ", " CABLE ", " PANEL ", " COUNTERPOISE "),
    ),
    Rule("kw_telecom_it", "ELECTRICAL", "TELECOM_IT", "kw_any", (" NETWORK ", " TELECOMMUNICATION", " VIDEO SURVEILLANCE ", " DATA ")),
    Rule(
        "kw_piping_drainage",
        "PIPING_DRAINAGE",
        "PIPING_UTILITY",
        "kw_any",
        (
            " PIPE ",
            " MANHOLE ",
            " CATCH BASIN",
            " DRAIN",
            " SEWER ",
            " VALVE ",
            " HYDRANT ",
            " PUMP STATION ",
            " STORMWATER ",
            " OUTFALL ",
            " INTAKE ",
            " WET WELL ",
        ),
    ),
    Rule(
        "kw_paving_earthwork",
        "ROADWORK_PAVING",
        "PAVING_EARTHWORK",
        "kw_any",
        (
            " ASPHALT ",
            " PAVEMENT ",
            " MILLING ",
            " EXCAVATION ",
            " BASE COURSE ",
            " SUBBASE ",
            " GROOVING ",
            " JOINT ",
            " SLURRY ",
            " TRENCH STABILIZATION ",
            " GEOTEXTILE ",
            " LEVEL 3 ",
            " CURB ",
            " SIDEWALK ",
        ),
    ),
    Rule(
        "kw_temp_traffic",
        "GENERAL_TEMPORARY",
        "TEMP_TRAFFIC_MOBILIZATION",
        "kw_any",
        (" MOBILIZATION ", " DEMOBILIZATION ", " TRAFFIC CONTROL ", " ESCORT ", " SURVEY ", " SWEEPER ", " SECURITY CONTROL "),
    ),
    Rule(
        "kw_landscape_env",
        "LANDSCAPE_ENVIRONMENTAL",
        "LANDSCAPING_REVEGETATION",
        "kw_any",
        (
            " SEEDING ",
            " TOPSOIL ",
            " PLANT ",
            " IRRIGATION ",
            " EROSION ",
            " SEDIMENT ",
            " WATTLE ",
            " RIPRAP ",
            " GRUBBING ",
            " LANDSCAPE ",
            " DEWATERING ",
            " INLET PROTECTION ",
            " DITCH PROTECTION ",
        ),
    ),
    Rule(
        "kw_demo_remediation",
        "DEMOLITION_REMEDIATION",
        "DEMOLITION_REMEDIATION",
        "kw_any",
        (" DEMOLITION ", " REMOVE ", " REMOVAL ", " CONTAMINATED "),
    ),
]


def assign_group(row: pd.Series) -> tuple[str, str, str]:
    spec = _norm(row.get("specification", ""))
    text = f" {_text_blob(spec, row.get('pay_item_description', ''), row.get('item_description_raw', ''))} "

    for rule in SPEC_RULES:
        if rule.kind == "spec_in" and spec in rule.values:
            return rule.item_group, rule.item_subgroup, rule.rule_id

    for rule in KEYWORD_RULES:
        if rule.kind == "kw_any" and _contains_any(text, rule.values):
            return rule.item_group, rule.item_subgroup, rule.rule_id

    return "OTHER_REVIEW", "UNCLASSIFIED_REVIEW", "fallback_unmapped"


def build_outputs(items: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    out = items.copy()
    assigned = out.apply(assign_group, axis=1, result_type="expand")
    assigned.columns = ["item_group", "item_subgroup", "grouping_rule_id"]
    out = pd.concat([out, assigned], axis=1)

    cols = [
        "item_id",
        "project_id",
        "line_no",
        "specification",
        "alternate_specification",
        "pay_item_description",
        "supplemental_description",
        "item_description_raw",
        "item",
        "quantity",
        "unit_norm",
        "item_group",
        "item_subgroup",
        "grouping_rule_id",
    ]
    proposal = out[cols].copy()

    group_summary = (
        proposal.groupby(["item_group", "item_subgroup"], dropna=False)
        .agg(item_rows=("item_id", "size"), distinct_items=("item", "nunique"), distinct_specs=("specification", "nunique"))
        .reset_index()
        .sort_values(["item_rows", "item_group", "item_subgroup"], ascending=[False, True, True], kind="stable")
    )
    group_summary["pct_rows"] = (group_summary["item_rows"] / len(proposal) * 100).round(2)

    unmapped = proposal[proposal["item_group"] == "OTHER_REVIEW"].copy()
    unmapped = (
        unmapped.groupby(["specification", "pay_item_description"], dropna=False)
        .agg(item_rows=("item_id", "size"), sample_item=("item", "first"))
        .reset_index()
        .sort_values(["item_rows", "specification", "pay_item_description"], ascending=[False, True, True], kind="stable")
    )

    return proposal, group_summary, unmapped


def main() -> None:
    parser = argparse.ArgumentParser(description="Propose traceable item group/subgroup taxonomy from Items.csv.")
    parser.add_argument("--items_csv", default="./data_out/Items.csv")
    parser.add_argument("--out_dir", default="./reports")
    args = parser.parse_args()

    items_path = Path(args.items_csv)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = pd.read_csv(items_path, keep_default_na=False)
    proposal, group_summary, unmapped = build_outputs(items)
    rulebook = pd.DataFrame(
        [
            {
                "rule_id": r.rule_id,
                "item_group": r.item_group,
                "item_subgroup": r.item_subgroup,
                "rule_kind": r.kind,
                "rule_values": "|".join(r.values),
                "rule_order": i + 1,
            }
            for i, r in enumerate(SPEC_RULES + KEYWORD_RULES)
        ]
    )

    proposal.to_csv(out_dir / "item_grouping_proposal.csv", index=False)
    group_summary.to_csv(out_dir / "item_grouping_summary.csv", index=False)
    unmapped.to_csv(out_dir / "item_grouping_unmapped_review.csv", index=False)
    rulebook.to_csv(out_dir / "item_grouping_rulebook.csv", index=False)

    print(f"Wrote {out_dir / 'item_grouping_proposal.csv'} ({len(proposal)} rows)")
    print(f"Wrote {out_dir / 'item_grouping_summary.csv'} ({len(group_summary)} rows)")
    print(f"Wrote {out_dir / 'item_grouping_unmapped_review.csv'} ({len(unmapped)} rows)")
    print(f"Wrote {out_dir / 'item_grouping_rulebook.csv'} ({len(rulebook)} rows)")


if __name__ == "__main__":
    main()
