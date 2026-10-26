"""Pipeline settings: where to read, where to write, and whether production writes are allowed.

Resolution order for each setting:
1. Databricks: a notebook widget, which is how job parameters reach notebook tasks.
2. Local runs and tests: an environment variable.
3. The default below.

| Setting | Widget / job parameter | Environment variable | Default |
|---|---|---|---|
| table_prefix | bidtab_table_prefix | BIDTAB_TABLE_PREFIX | `pop-poc`.`bidtab` |
| volume_root (inputs) | bidtab_volume_root | BIDTAB_VOLUME_ROOT | /Volumes/pop-poc/bidtab |
| exports_root | bidtab_exports_root | BIDTAB_EXPORTS_ROOT | <volume_root>/exports |
| allow_production_write | bidtab_allow_production_write | BIDTAB_ALLOW_PRODUCTION_WRITE | false |
| pdf_target_prefix | bidtab_pdf_target_prefix | BIDTAB_PDF_TARGET_PREFIX | none (pending Port IT) |

Write guard: code that writes a table or an export calls require_table_write()
or require_export_write(). Writing to the production schema `pop-poc`.`bidtab`
or under /Volumes/pop-poc/bidtab/ is refused unless allow_production_write is
true. Only the production job definition sets it, so staff still click one job.
An isolated run (Gate 2c, tests) names its own table_prefix and exports_root.

INCLUDE_ENG_EST is not here: it stays a literal in notebook 04, where the
Maintenance Guide tells analysts to flip it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Any

PROD_TABLE_PREFIX = "`pop-poc`.`bidtab`"
PROD_VOLUME_ROOT = "/Volumes/pop-poc/bidtab"

_TRUE = {"true", "1", "yes"}
_FALSE = {"false", "0", "no", ""}


class ProductionWriteRefused(PermissionError):
    """Raised when code would write to production without allow_production_write."""


class SettingMissing(ValueError):
    """Raised when a setting with no default is needed but not set."""


def _normalize_prefix(prefix: str) -> str:
    return prefix.replace("`", "").replace(" ", "").lower()


def _parse_bool(name: str, value: str) -> bool:
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise ValueError(f"{name} must be true or false, got {value!r}")


@dataclass(frozen=True)
class Settings:
    table_prefix: str = PROD_TABLE_PREFIX
    volume_root: str = PROD_VOLUME_ROOT
    exports_root: str | None = None
    allow_production_write: bool = False
    pdf_target_prefix: str | None = None

    # --- resolution ----------------------------------------------------------

    @classmethod
    def resolve(cls, dbutils: Any = None) -> Settings:
        """Widgets (Databricks) first, then environment variables, then defaults."""
        values: dict[str, Any] = {}
        for f in fields(cls):
            raw = _widget(dbutils, f"bidtab_{f.name}")
            if raw is None:
                raw = os.environ.get(f"BIDTAB_{f.name.upper()}") or None
            if raw is None:
                continue
            if f.name == "allow_production_write":
                values[f.name] = _parse_bool(f.name, raw)
            else:
                values[f.name] = raw.rstrip("/") if f.name.endswith("_root") else raw
        return cls(**values)

    @classmethod
    def from_environment(cls) -> Settings:
        """Environment variables and defaults only (local runs)."""
        return cls.resolve(None)

    # --- names and paths -----------------------------------------------------

    def table(self, name: str) -> str:
        """Fully qualified, quoted table name, e.g. `pop-poc`.`bidtab`.`mart_bid_analysis`."""
        return f"{self.table_prefix}.`{name}`"

    def volume(self, name: str) -> str:
        """Path of an input volume directory, e.g. /Volumes/pop-poc/bidtab/source_files."""
        return f"{self.volume_root}/{name}"

    def config_file(self, filename: str) -> str:
        return f"{self.volume('config')}/{filename}"

    @property
    def exports_dir(self) -> str:
        return self.exports_root or self.volume("exports")

    def pdf_table(self, name: str) -> str:
        """Table in the isolated PDF target. Never the production schema (NFR-05)."""
        if not self.pdf_target_prefix:
            raise SettingMissing(
                "pdf_target_prefix is not set. The PDF path writes only to an isolated schema or prefix "
                "(BRD open question 3, pending Port IT). Set bidtab_pdf_target_prefix."
            )
        if _normalize_prefix(self.pdf_target_prefix) == _normalize_prefix(PROD_TABLE_PREFIX):
            raise ProductionWriteRefused("pdf_target_prefix must not be the production schema (NFR-05).")
        return f"{self.pdf_target_prefix}.`{name}`"

    # --- write guard ---------------------------------------------------------

    @property
    def tables_are_production(self) -> bool:
        return _normalize_prefix(self.table_prefix) == _normalize_prefix(PROD_TABLE_PREFIX)

    @property
    def exports_are_production(self) -> bool:
        path = self.exports_dir.rstrip("/")
        return path == PROD_VOLUME_ROOT or path.startswith(PROD_VOLUME_ROOT + "/")

    def require_table_write(self) -> None:
        if self.tables_are_production and not self.allow_production_write:
            raise ProductionWriteRefused(
                f"Refusing to write to the production schema {PROD_TABLE_PREFIX}. "
                "Set bidtab_table_prefix to an isolated schema, or set "
                "bidtab_allow_production_write=true (production job definition only)."
            )

    def require_export_write(self) -> None:
        if self.exports_are_production and not self.allow_production_write:
            raise ProductionWriteRefused(
                f"Refusing to write exports under {PROD_VOLUME_ROOT}. "
                "Set bidtab_exports_root to an isolated location, or set "
                "bidtab_allow_production_write=true (production job definition only)."
            )


def _widget(dbutils: Any, name: str) -> str | None:
    """A widget's value, or None when there is no dbutils, no widgets, or no such widget."""
    widgets = getattr(dbutils, "widgets", None)
    if widgets is None:
        return None
    try:
        value = widgets.get(name)
    except Exception:  # Databricks raises a Py4J error for an undefined widget
        return None
    return value or None
