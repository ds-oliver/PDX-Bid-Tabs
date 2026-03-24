#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bidtabs.extract import build_raw_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Build raw snapshot CSV at bidder-line grain directly from bid tab workbooks.")
    parser.add_argument("--input_dir", default="./data_in")
    parser.add_argument("--output_csv", default="./data_out/compiled_excel_itemized_raw_snapshot.csv")
    args = parser.parse_args()

    output_csv = Path(args.output_csv)
    df = build_raw_snapshot(args.input_dir)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"Wrote {output_csv} ({len(df)} rows)")


if __name__ == "__main__":
    main()
