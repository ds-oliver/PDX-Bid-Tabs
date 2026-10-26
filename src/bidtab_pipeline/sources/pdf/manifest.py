"""PDF landing and file manifest (FR-01 to FR-03).

- FR-01: PDFs land in their own volume (Settings.pdf_landing), top level only.
- FR-02: every file gets a manifest row: path, SHA-256, size, page count,
  producer, first-seen time, parse status. A file whose content hash was already
  seen in this run is marked duplicate and not parsed again.
- FR-03: non-PDFs, unreadable PDFs, and PDFs without a text layer are rejected
  with a reason.

parse_status values: parsed, flagged (unknown layout, no rows emitted),
rejected (FR-03), duplicate, error (unexpected exception). error_text says why
a file was not parsed and is NULL on a parsed file; parse warnings on a parsed
file go in warning_text (D-04).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pdfplumber

from bidtab_pipeline.io.volumes import list_entry_names

PDF_MAGIC = b"%PDF-"


@dataclass(frozen=True)
class FileCheck:
    file_name: str
    file_path: str
    file_sha256: str
    file_size_bytes: int
    page_count: int | None
    producer: str | None
    has_text_layer: bool | None
    rejection: str | None  # FR-03 reason code
    rejection_detail: str | None


def list_landing_files(landing: str, dbutils: Any = None) -> list[str]:
    """Top-level files in the landing volume, sorted. Subfolders and Office lock files are ignored."""
    return sorted(n for n in list_entry_names(landing, dbutils) if not n.endswith("/") and not n.startswith("~$"))


def check_file(path: str) -> FileCheck:
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    name = Path(path).name

    def result(pages=None, producer=None, text=None, rejection=None, detail=None):
        return FileCheck(name, path, sha, len(data), pages, producer, text, rejection, detail)

    if not name.lower().endswith(".pdf") or not data.startswith(PDF_MAGIC):
        return result(rejection="not_pdf", detail="extension is not .pdf or content does not start with %PDF-")
    try:
        with pdfplumber.open(path) as pdf:
            pages = len(pdf.pages)
            producer = (pdf.metadata or {}).get("Producer")
            has_text = any(page.chars for page in pdf.pages)
    except Exception as exc:  # pdfminer raises several types for damaged files
        return result(rejection="unreadable_pdf", detail=f"{type(exc).__name__}: {exc}")
    if not has_text:
        return result(pages, producer, False, "no_text_layer", "no text on any page; OCR is out of MVP scope (FR-18)")
    return result(pages, producer, True)


def manifest_row(
    check: FileCheck,
    first_seen_at: datetime,
    parsed_at: datetime,
    parse_status: str,
    status_reason: str | None = None,
    error_text: str | None = None,
    warning_text: str | None = None,
    ean: str | None = None,
    solicitation_no: str | None = None,
    item_rows: int = 0,
    control_total_rows: int = 0,
) -> dict[str, Any]:
    return {
        "file_name": check.file_name,
        "file_path": check.file_path,
        "file_sha256": check.file_sha256,
        "file_size_bytes": check.file_size_bytes,
        "page_count": check.page_count,
        "producer": check.producer,
        "has_text_layer": check.has_text_layer,
        "first_seen_at": first_seen_at,
        "parse_status": parse_status,
        "status_reason": status_reason,
        "error_text": error_text,
        "warning_text": warning_text,
        "ean": ean,
        "solicitation_no": solicitation_no,
        "item_rows": item_rows,
        "control_total_rows": control_total_rows,
        "parsed_at": parsed_at,
    }
