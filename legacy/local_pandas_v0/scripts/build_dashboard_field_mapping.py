#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.reporting import (
    DASHBOARD_FIELD_MAPPING_HEADERS as HEADERS,
    build_dashboard_field_mapping_artifacts,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build object-level dashboard field mapping workbook.")
    parser.add_argument("--source_csv", default="./docs/data_dictionary/odot_to_port_field_mapping_source.csv")
    parser.add_argument("--raw_csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    parser.add_argument("--clean_csv", default="./data_out/compiled_excel_itemized_clean.csv")
    parser.add_argument("--out_xlsx", default="./docs/dashboard_field_mapping.xlsx")
    parser.add_argument("--out_md", default="./docs/dashboard_field_mapping.md")
    args = parser.parse_args()

    build_dashboard_field_mapping_artifacts(
        source_csv=args.source_csv,
        raw_csv=args.raw_csv,
        clean_csv=args.clean_csv,
        out_xlsx=args.out_xlsx,
        out_md=args.out_md,
    )
    print(f"Wrote {Path(args.out_xlsx)}")
    print(f"Wrote {Path(args.out_md)}")


if __name__ == "__main__":
    main()
