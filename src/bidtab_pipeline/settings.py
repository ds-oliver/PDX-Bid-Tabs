"""Pipeline settings: table namespace and volume root.

Defaults are the production values from the 2026-05-28 baseline, so a job run
on Databricks needs no configuration. Local runs and tests override them with
environment variables:

    BIDTAB_TABLE_PREFIX   default `pop-poc`.`bidtab`   (quoted; the catalog has a hyphen)
    BIDTAB_VOLUME_ROOT    default /Volumes/pop-poc/bidtab

INCLUDE_ENG_EST is not here: it stays a literal in notebook 04, where the
Maintenance Guide tells analysts to flip it.

The PDF path's target prefix is pending Port IT (BRD open question 3). It will
be added here as a setting, never a literal (NFR-05).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

PROD_TABLE_PREFIX = "`pop-poc`.`bidtab`"
PROD_VOLUME_ROOT = "/Volumes/pop-poc/bidtab"


@dataclass(frozen=True)
class Settings:
    table_prefix: str = PROD_TABLE_PREFIX
    volume_root: str = PROD_VOLUME_ROOT

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            table_prefix=os.environ.get("BIDTAB_TABLE_PREFIX", PROD_TABLE_PREFIX),
            volume_root=os.environ.get("BIDTAB_VOLUME_ROOT", PROD_VOLUME_ROOT).rstrip("/"),
        )

    def table(self, name: str) -> str:
        """Fully qualified, quoted table name, e.g. `pop-poc`.`bidtab`.`mart_bid_analysis`."""
        return f"{self.table_prefix}.`{name}`"

    def volume(self, name: str) -> str:
        """Path of a volume directory, e.g. /Volumes/pop-poc/bidtab/source_files."""
        return f"{self.volume_root}/{name}"

    def config_file(self, filename: str) -> str:
        return f"{self.volume('config')}/{filename}"
