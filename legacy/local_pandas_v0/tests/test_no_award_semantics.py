import re
from pathlib import Path

import pandas as pd

from bidtabs.schemas import COMPILED_COLUMNS, STAR_SCHEMAS


FORBIDDEN = re.compile(r"(?i)award|awarded|accepted|selected_bidder|award_source")


def test_schema_has_no_award_language():
    for col in COMPILED_COLUMNS:
        assert not FORBIDDEN.search(col.name)
    for cols in STAR_SCHEMAS.values():
        for col in cols:
            assert not FORBIDDEN.search(col.name)


def test_outputs_have_no_award_columns():
    out_dir = Path("data_out")
    if not out_dir.exists():
        return
    for csv_path in out_dir.glob("*.csv"):
        df = pd.read_csv(csv_path, nrows=1, keep_default_na=False)
        for col in df.columns:
            assert not FORBIDDEN.search(col)


def test_metrics_columns_are_bid_only(tmp_path):
    # Build tiny fixture data to run metrics without award-like fields.
    facts_dir = tmp_path / "facts"
    facts_dir.mkdir()

    pd.DataFrame(
        [
            {
                "project_id": 1,
                "bid_schedule_id": 10,
                "pay_item_id": 100,
                "bidder_id": 1000,
                "unit_price": 5.0,
            },
            {
                "project_id": 1,
                "bid_schedule_id": 10,
                "pay_item_id": 100,
                "bidder_id": 1001,
                "unit_price": 6.0,
            },
        ]
    ).to_csv(facts_dir / "fact_bid_item_price.csv", index=False)

    pd.DataFrame(
        [
            {"bidder_id": 1000, "bidder_type": "CONTRACTOR"},
            {"bidder_id": 1001, "bidder_type": "CONTRACTOR"},
        ]
    ).to_csv(facts_dir / "dim_bidder.csv", index=False)

    from scripts import build_metrics

    build_metrics.main = build_metrics.main  # silence lint; ensures import
    # Run script via function by emulating CLI
    import subprocess, sys
    subprocess.check_call(
        [sys.executable, "scripts/build_metrics.py", "--facts_dir", str(facts_dir), "--output_dir", str(facts_dir), "--emit_metrics"]
    )

    df = pd.read_csv(facts_dir / "fact_project_pay_item_metrics.csv")
    for col in df.columns:
        assert not FORBIDDEN.search(col)
    forbidden_derived = ["apparent_low", "low_bid", "selected"]
    for col in df.columns:
        for token in forbidden_derived:
            assert token not in col

