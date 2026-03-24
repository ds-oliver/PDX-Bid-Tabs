from __future__ import annotations

import argparse
from pathlib import Path

from .extract import build_raw_snapshot, write_extract_outputs
from .model import write_model_outputs
from .reporting import build_reports


def _cmd_extract(args: argparse.Namespace) -> None:
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_csv = out_dir / "compiled_excel_itemized_raw_snapshot.csv"
    clean_csv = out_dir / "compiled_excel_itemized_clean.csv"

    raw_df = build_raw_snapshot(args.input_dir)
    raw_df.to_csv(raw_csv, index=False)
    write_extract_outputs(
        input_dir=args.input_dir,
        output_csv=clean_csv,
        run_id=args.run_id,
        reports_dir=args.reports_dir,
        config_dir=args.config_dir,
        arith_tolerance=args.arith_tolerance,
    )
    print(f"Wrote {raw_csv}")
    print(f"Wrote {clean_csv}")


def _cmd_build_model(args: argparse.Namespace) -> None:
    write_model_outputs(args.clean_csv, args.out_dir, args.config_dir)
    print(f"Wrote model outputs to {args.out_dir}")


def _cmd_build_reports(args: argparse.Namespace) -> None:
    selected = [part.strip() for part in args.reports.split(",") if part.strip()]
    build_reports(
        {
            "clean_csv": args.clean_csv,
            "raw_snapshot_csv": args.raw_snapshot_csv,
            "reports_dir": args.reports_dir,
            "catalog_xlsx": args.catalog_xlsx,
            "spec_catalog_csv": args.spec_catalog_csv,
            "similarity_csv": args.similarity_csv,
            "similarity_xlsx": args.similarity_xlsx,
            "variability_xlsx": args.variability_xlsx,
            "variability_prefix": args.variability_prefix,
            "crosswalk_prefix": args.crosswalk_prefix,
            "mapping_source_csv": args.mapping_source_csv,
            "dashboard_xlsx": args.dashboard_xlsx,
            "dashboard_md": args.dashboard_md,
        },
        selected,
    )
    print(f"Built reports: {', '.join(selected)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Notebook-portable bid tabs pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract = subparsers.add_parser("extract", help="Build raw snapshot and clean staging extract")
    extract.add_argument("--input-dir", default="./data_in")
    extract.add_argument("--out-dir", default="./data_out")
    extract.add_argument("--reports-dir", default="./reports")
    extract.add_argument("--config-dir", default="./config")
    extract.add_argument("--run-id", default="local")
    extract.add_argument("--arith-tolerance", type=float, default=0.02)
    extract.set_defaults(func=_cmd_extract)

    model = subparsers.add_parser("build-model", help="Build canonical fact and dimensions")
    model.add_argument("--clean-csv", default="./data_out/compiled_excel_itemized_clean.csv")
    model.add_argument("--out-dir", default="./data_out")
    model.add_argument("--config-dir", default="./config")
    model.set_defaults(func=_cmd_build_model)

    reports = subparsers.add_parser("build-reports", help="Build optional reporting artifacts")
    reports.add_argument("--reports", default="pay-item-similarity,item-variability,estimate-crosswalk,dashboard-field-mapping")
    reports.add_argument("--clean-csv", default="./data_out/compiled_excel_itemized_clean.csv")
    reports.add_argument("--raw-snapshot-csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    reports.add_argument("--reports-dir", default="./reports")
    reports.add_argument("--catalog-xlsx", default="./data_in/DRAFT One Port Estimating - Quantities Tool.xlsx")
    reports.add_argument("--spec-catalog-csv", default="./config/spec_section_catalog.csv")
    reports.add_argument("--similarity-csv", default="./reports/pay_item_similarity_review.csv")
    reports.add_argument("--similarity-xlsx", default="./reports/pay_item_similarity_review.xlsx")
    reports.add_argument("--variability-xlsx", default="./reports/item_variability_business_report.xlsx")
    reports.add_argument("--variability-prefix", default="item_variability")
    reports.add_argument("--crosswalk-prefix", default="estimate_item_crosswalk")
    reports.add_argument("--mapping-source-csv", default="./docs/data_dictionary/odot_to_port_field_mapping_source.csv")
    reports.add_argument("--dashboard-xlsx", default="./docs/dashboard_field_mapping.xlsx")
    reports.add_argument("--dashboard-md", default="./docs/dashboard_field_mapping.md")
    reports.set_defaults(func=_cmd_build_reports)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
