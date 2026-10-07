from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd


DEFAULT_CONFIG_FILES: Dict[str, str] = {
    "contractor_name_map": "contractor_name_map.csv",
    "location_dictionary": "location_dictionary.csv",
    "pay_item_parse_overrides": "pay_item_parse_overrides.csv",
    "spec_section_catalog": "spec_section_catalog.csv",
}


def read_csv_if_exists(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, keep_default_na=False)


def load_config_tables(config_dir: str | Path) -> dict[str, pd.DataFrame]:
    root = Path(config_dir)
    return {name: read_csv_if_exists(root / filename) for name, filename in DEFAULT_CONFIG_FILES.items()}


def load_location_dictionary(config_dir: str | Path) -> pd.DataFrame:
    return read_csv_if_exists(Path(config_dir) / DEFAULT_CONFIG_FILES["location_dictionary"])


def load_name_map_table(config_dir: str | Path) -> pd.DataFrame:
    return read_csv_if_exists(Path(config_dir) / DEFAULT_CONFIG_FILES["contractor_name_map"])


def load_parse_override_table(config_dir: str | Path) -> pd.DataFrame:
    return read_csv_if_exists(Path(config_dir) / DEFAULT_CONFIG_FILES["pay_item_parse_overrides"])
