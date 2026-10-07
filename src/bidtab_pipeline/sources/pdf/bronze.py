"""PDF Bronze: manifest, items, and control totals (DR-01 to DR-03).

ingest_landing() is plain Python: it checks, de-duplicates, and parses every
file in the landing volume and returns rows shaped like the contracts.
build_pdf_bronze() writes them to the isolated PDF target with Spark. It never
writes to the production schema (Settings.pdf_table refuses it, NFR-05).

bid_type follows the workbook sheet names the xlsx path uses, so the shared
Silver SQL classifies tabs the same way ('%Alternate%' -> ALT):
- one base schedule: "Base Bid Tab"; several (2023-10383 Schedules A and B):
  "Base Bid Tab - <schedule label>", which keeps natural keys distinct.
- one alternate: "Alternate Bid Tab"; several: "Alternate Bid Tab <n>" by order.
This mapping is provisional until the Phase 4 parity check against the xlsx
mart for the overlap set; schedule_label keeps the PDF's own wording.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from bidtab_pipeline.contracts import BRONZE_PDF_BID_ITEMS, BRONZE_PDF_CONTROL_TOTALS, REF_FILE_MANIFEST
from bidtab_pipeline.quality.reconciliation import Check, reconcile
from bidtab_pipeline.sources.pdf.manifest import check_file, list_landing_files, manifest_row
from bidtab_pipeline.sources.pdf.model import LayoutFlag, ParsedBidTab, Schedule
from bidtab_pipeline.sources.pdf.parser import bidder_key, parse_bid_tab, schedule_kind

MANIFEST_TABLE = "ref_file_manifest"
ITEMS_TABLE = "bronze_pdf_bid_items"
CONTROL_TOTALS_TABLE = "bronze_pdf_control_totals"


def bid_type(schedule: Schedule, schedules: list[Schedule]) -> str:
    same_kind = [s for s in schedules if s.kind == schedule.kind]
    if schedule.kind == "base":
        return "Base Bid Tab" if len(same_kind) == 1 else f"Base Bid Tab - {schedule.label}"
    if len(same_kind) == 1:
        return "Alternate Bid Tab"
    return f"Alternate Bid Tab {same_kind.index(schedule) + 1}"


def item_rows(parsed: ParsedBidTab, file_sha256: str) -> list[dict[str, Any]]:
    header = parsed.detail_header or parsed.header
    by_order = {s.order: s for s in parsed.schedules}
    rows = []
    for item in parsed.items:
        schedule = by_order[item.schedule_order]
        rows.append(
            {
                "source_file": parsed.file_name,
                "source_sheet": item.schedule_label,
                "bid_type": bid_type(schedule, parsed.schedules),
                "ean": header.ean,
                "project_name": header.project_name_raw,
                "airport_name": header.location_raw,
                "solicitation_no": header.solicitation_no,
                "bid_date": header.bid_date,
                "item_no": item.item_no,
                "item_description_raw": item.description,
                "estimated_quantity": item.quantity,
                "unit": item.unit or None,
                "contractor_name": item.bidder,
                "contractor_position": item.contractor_position,
                "is_engineers_estimate": item.is_engineers_estimate,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "is_section_header": False,
                "page_no": item.page_no,
                "spec_ref_raw": item.spec_ref_raw,
                "spec_ref_type": item.spec_ref_type,
                "schedule_label": item.schedule_label,
                "schedule_kind": item.schedule_kind,
                "schedule_order": item.schedule_order,
                "file_sha256": file_sha256,
            }
        )
    return rows


def control_total_rows(parsed: ParsedBidTab, file_sha256: str) -> list[dict[str, Any]]:
    header = parsed.header
    positions = {bidder_key(i.bidder): (i.bidder, i.contractor_position) for i in parsed.items}
    targets = {t.column_index: t for t in parsed.summary_targets}
    base = {
        "source_file": parsed.file_name,
        "file_sha256": file_sha256,
        "ean": header.ean,
        "solicitation_no": header.solicitation_no,
    }
    rows = []
    for t in parsed.summary_totals:
        name, position = positions[bidder_key(t.bidder_name_raw)]
        orders = targets[t.column_index].schedule_orders
        rows.append(
            {
                **base,
                "total_source": "summary",
                "schedule_label": t.column_label,
                "schedule_kind": schedule_kind(t.column_label),
                "schedule_order": orders[0] if len(orders) == 1 else None,
                "bidder_name_raw": t.bidder_name_raw,
                "contractor_name": name,
                "contractor_position": position,
                "is_engineers_estimate": t.is_engineers_estimate,
                "total_amount": t.amount,
                "is_starred": t.is_starred,
                "footnote_text": parsed.footnote_text if t.is_starred else None,
                "is_corrected_total": parsed.is_corrected_footnote if t.is_starred else False,
                "page_no": t.page_no,
            }
        )
    for t in parsed.detail_totals:
        rows.append(
            {
                **base,
                "total_source": "detail",
                "schedule_label": t.label,
                "schedule_kind": t.kind,
                "schedule_order": t.schedule_order,
                "bidder_name_raw": t.bidder,
                "contractor_name": t.bidder,
                "contractor_position": t.contractor_position,
                "is_engineers_estimate": t.is_engineers_estimate,
                "total_amount": t.amount,
                "is_starred": False,
                "footnote_text": None,
                "is_corrected_total": False,
                "page_no": t.page_no,
            }
        )
    return rows


@dataclass
class IngestResult:
    manifest: list[dict[str, Any]] = field(default_factory=list)
    items: list[dict[str, Any]] = field(default_factory=list)
    control_totals: list[dict[str, Any]] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)


def ingest_landing(
    landing: str,
    first_seen: dict[str, datetime] | None = None,
    now: datetime | None = None,
    dbutils: Any = None,
) -> IngestResult:
    """Check, de-duplicate, and parse every top-level file in the landing volume.

    first_seen maps file SHA-256 to the first_seen_at already recorded in the
    manifest, so a re-run keeps the original time (FR-02).
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    first_seen = first_seen or {}
    result = IngestResult()
    seen: dict[str, str] = {}
    for name in list_landing_files(landing, dbutils):
        check = check_file(f"{landing}/{name}")
        when = first_seen.get(check.file_sha256, now)
        if check.rejection:
            result.manifest.append(manifest_row(check, when, now, "rejected", check.rejection, check.rejection_detail))
            continue
        if check.file_sha256 in seen:
            result.manifest.append(
                manifest_row(check, when, now, "duplicate", "same_hash", f"same content as {seen[check.file_sha256]}")
            )
            continue
        seen[check.file_sha256] = name
        try:
            parsed = parse_bid_tab(check.file_path)
        except LayoutFlag as flag:
            result.manifest.append(manifest_row(check, when, now, "flagged", flag.code, str(flag)))
            continue
        except Exception as exc:
            result.manifest.append(manifest_row(check, when, now, "error", type(exc).__name__, str(exc)))
            continue
        items = item_rows(parsed, check.file_sha256)
        totals = control_total_rows(parsed, check.file_sha256)
        result.items.extend(items)
        result.control_totals.extend(totals)
        result.checks.extend(reconcile(parsed))
        warnings = "; ".join(f"warning: {w}" for w in parsed.warnings) or None
        result.manifest.append(
            manifest_row(
                check,
                when,
                now,
                "parsed",
                None,
                warnings,
                parsed.header.ean,
                parsed.header.solicitation_no,
                len(items),
                len(totals),
            )
        )
    return result


def build_pdf_bronze(spark, settings, dbutils: Any = None) -> IngestResult:
    """Ingest the landing volume and overwrite the three PDF Bronze tables in the isolated target."""
    from pyspark.sql.functions import current_timestamp

    from bidtab_pipeline.io.spark_schema import struct_type

    manifest_table = settings.pdf_table(MANIFEST_TABLE)  # raises unless an isolated target is set
    items_table = settings.pdf_table(ITEMS_TABLE)
    totals_table = settings.pdf_table(CONTROL_TOTALS_TABLE)
    landing = settings.pdf_landing

    from pyspark.errors import AnalysisException

    first_seen: dict[str, datetime] = {}
    try:
        prior = spark.table(manifest_table).select("file_sha256", "first_seen_at").collect()
    except AnalysisException:  # first run: no manifest yet
        prior = []
    for row in prior:
        if row.first_seen_at is not None:
            first_seen.setdefault(row.file_sha256, row.first_seen_at)

    result = ingest_landing(landing, first_seen, dbutils=dbutils)

    def write(rows, columns, table, loaded_at: bool):
        schema = struct_type(columns, exclude=("bronze_loaded_at",) if loaded_at else ())
        df = spark.createDataFrame(rows, schema=schema)
        if loaded_at:
            df = df.withColumn("bronze_loaded_at", current_timestamp())
        df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(table)

    write(result.manifest, REF_FILE_MANIFEST, manifest_table, loaded_at=False)
    write(result.items, BRONZE_PDF_BID_ITEMS, items_table, loaded_at=True)
    write(result.control_totals, BRONZE_PDF_CONTROL_TOTALS, totals_table, loaded_at=True)

    print("file | status | item_rows | reason")
    for m in result.manifest:
        print(f"{m['file_name']} | {m['parse_status']} | {m['item_rows']} | {m['status_reason'] or ''}")
    passed = sum(c.passed for c in result.checks if c.check == "summary")
    total = sum(1 for c in result.checks if c.check == "summary")
    print("\nFINAL SUMMARY")
    print(f"files_seen={len(result.manifest)}")
    for status in ("parsed", "flagged", "rejected", "duplicate", "error"):
        print(f"files_{status}={sum(m['parse_status'] == status for m in result.manifest)}")
    print(f"item_rows_written={len(result.items)}")
    print(f"control_total_rows_written={len(result.control_totals)}")
    print(f"summary_totals_reconciled={passed}/{total}")
    return result
