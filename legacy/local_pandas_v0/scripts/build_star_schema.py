#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.model import (
    _extract_alt_code,
    build_analysis_tables,
    build_dim_pay_item,
    build_dim_project,
    write_model_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build analytical outputs from compiled extract")
    parser.add_argument("--input_csv", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--config_dir", default="./config")
    args = parser.parse_args()

    write_model_outputs(args.input_csv, args.output_dir, args.config_dir)
    print(f"Wrote analytical outputs to {Path(args.output_dir)}")


if __name__ == "__main__":
    main()
