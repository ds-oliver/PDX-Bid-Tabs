from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.analyze_pay_item_similarity import (
    attach_spec_descriptions,
    build_detail_frame as build_similarity_detail_frame,
    build_high_variance_details,
    build_summary as build_similarity_summary,
    extract_alt_spec_code,
    extract_spec_code,
    load_spec_descriptions,
    write_workbook as write_similarity_workbook,
)
from scripts.build_item_variability_business_report import build_report as _build_item_variability_report
from scripts.update_field_mapping_examples import (
    OUT_HEADERS as DASHBOARD_FIELD_MAPPING_HEADERS,
    build_mapping as build_dashboard_mapping,
    write_md as write_dashboard_mapping_md,
    write_xlsx as write_dashboard_mapping_xlsx,
)


def build_pay_item_similarity_artifacts(
    compiled: pd.DataFrame,
    spec_catalog_csv: Path | str,
    output_csv: Path | str,
    output_xlsx: Path | str,
) -> dict[str, pd.DataFrame]:
    spec_map = load_spec_descriptions(Path(spec_catalog_csv))
    detail = build_similarity_detail_frame(compiled)
    summary = build_similarity_summary(detail)
    high = build_high_variance_details(detail, summary)
    summary.insert(1, "Spec Description", attach_spec_descriptions(summary, spec_map))
    spec_idx = high.columns.get_loc("Specification")
    high.insert(spec_idx + 1, "Spec Description", attach_spec_descriptions(high, spec_map))

    output_csv = Path(output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_csv, index=False)
    write_similarity_workbook(summary, high, Path(output_xlsx))
    return {"summary": summary, "high": high}


def build_dashboard_field_mapping_artifacts(
    source_csv: Path | str,
    raw_csv: Path | str,
    clean_csv: Path | str | None,
    out_xlsx: Path | str,
    out_md: Path | str,
) -> pd.DataFrame:
    clean_path = Path(clean_csv) if clean_csv else None
    df = build_dashboard_mapping(
        Path(source_csv),
        Path(raw_csv),
        clean_path if clean_path and clean_path.exists() else None,
    )
    write_dashboard_mapping_xlsx(df, Path(out_xlsx))
    write_dashboard_mapping_md(df, Path(out_md))
    return df


def build_item_variability_artifacts(
    raw_snapshot_csv: Path | str,
    clean_csv: Path | str | None,
    out_xlsx: Path | str,
    out_dir: Path | str,
    prefix: str,
) -> None:
    clean_path = Path(clean_csv) if clean_csv else None
    if clean_path is not None and not clean_path.exists():
        clean_path = None
    _build_item_variability_report(
        raw_snapshot_csv=Path(raw_snapshot_csv),
        clean_csv=clean_path,
        out_xlsx=Path(out_xlsx),
        out_dir=Path(out_dir),
        prefix=prefix,
    )


def build_estimate_item_crosswalk_artifacts(
    input_csv: Path | str,
    catalog_xlsx: Path | str,
    out_dir: Path | str,
    out_prefix: str,
) -> dict[str, pd.DataFrame | Path]:
    from scripts import build_estimate_item_crosswalk as legacy

    legacy.CSV_PATH = Path(input_csv)
    legacy.CATALOG_XLSX = Path(catalog_xlsx)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    legacy.OUTPUT_PATH = out_dir / f"{out_prefix}.xlsx"

    detail, table = legacy.run_crosswalk()
    detail.to_csv(out_dir / f"{out_prefix}_detail.csv", index=False)
    table.to_csv(out_dir / f"{out_prefix}_table.csv", index=False)
    detail[detail["mapping_status"] == "unmapped"].to_csv(out_dir / f"{out_prefix}_unmapped.csv", index=False)
    detail[detail["mapping_status"] == "out_of_catalog_scope"].to_csv(
        out_dir / f"{out_prefix}_out_of_catalog_scope.csv",
        index=False,
    )
    legacy.write_xlsx(detail, table)
    return {"detail": detail, "table": table, "xlsx": legacy.OUTPUT_PATH}


def build_reports(inputs: dict[str, Path | str | None], selected_reports: list[str]) -> dict[str, object]:
    outputs: dict[str, object] = {}
    for report in selected_reports:
        if report == "pay-item-similarity":
            compiled = pd.read_csv(Path(inputs["clean_csv"]), keep_default_na=False)
            outputs[report] = build_pay_item_similarity_artifacts(
                compiled,
                inputs["spec_catalog_csv"],
                inputs["similarity_csv"],
                inputs["similarity_xlsx"],
            )
        elif report == "item-variability":
            outputs[report] = build_item_variability_artifacts(
                inputs["raw_snapshot_csv"],
                inputs.get("clean_csv"),
                inputs["variability_xlsx"],
                inputs["reports_dir"],
                str(inputs.get("variability_prefix", "item_variability")),
            )
        elif report == "estimate-crosswalk":
            outputs[report] = build_estimate_item_crosswalk_artifacts(
                inputs["clean_csv"],
                inputs["catalog_xlsx"],
                inputs["reports_dir"],
                str(inputs.get("crosswalk_prefix", "estimate_item_crosswalk")),
            )
        elif report == "dashboard-field-mapping":
            outputs[report] = build_dashboard_field_mapping_artifacts(
                inputs["mapping_source_csv"],
                inputs["raw_snapshot_csv"],
                inputs.get("clean_csv"),
                inputs["dashboard_xlsx"],
                inputs["dashboard_md"],
            )
        else:
            raise ValueError(f"Unsupported report: {report}")
    return outputs
