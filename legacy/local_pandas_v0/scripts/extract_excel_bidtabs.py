#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.extract import write_extract_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract bid tab Excel files into compiled canonical csv (v2).")
    parser.add_argument("--input_dir", required=True)
    parser.add_argument("--output_csv", required=True)
    parser.add_argument("--run_id", required=True)
    parser.add_argument("--reports_dir", default="./reports")
    parser.add_argument("--config_dir", default="./config")
    parser.add_argument("--arith_tolerance", type=float, default=0.02)
    parser.add_argument("--totals_tolerance_amount", type=float, default=5.0)
    parser.add_argument("--totals_tolerance_pct", type=float, default=0.02)
    args = parser.parse_args()

    df = write_extract_outputs(
        input_dir=args.input_dir,
        output_csv=args.output_csv,
        run_id=args.run_id,
        reports_dir=args.reports_dir,
        config_dir=args.config_dir,
        arith_tolerance=args.arith_tolerance,
        totals_tolerance_amount=args.totals_tolerance_amount,
        totals_tolerance_pct=args.totals_tolerance_pct,
    )
    print(f"Wrote {Path(args.output_csv)} ({len(df)} rows)")


if __name__ == "__main__":
    main()
