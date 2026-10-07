"""Generate the synthetic xlsx fixtures. Run from the repo root:

    .venv/bin/python tests/fixtures/build_synthetic_fixtures.py

All names, numbers, and projects are invented. Each workbook targets parser
paths in reference notebook 01; the comments name the path.

Outputs:
- tests/fixtures/xlsx_synthetic/source_files/        the source_files volume (first run)
- tests/fixtures/xlsx_synthetic/source_files_run2/   replacements copied over it for the second run
- tests/fixtures/config_synthetic/AwardedBidsSearchList.xlsx
- tests/fixtures/config_synthetic_run2/AwardedBidsSearchList.xlsx
The CSV configs are hand-written, not generated.

The second run exercises every status of 04's post-run Delta report:
SYN_A and SYN_D unchanged, SYN_B removed, SYN_C new, SYN_E rows changed,
SYN_F bidders changed (same row count), SYN_G awarded bidder changed (award
list), SYN_H unmapped count changed (crosswalk row added).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "xlsx_synthetic" / "source_files"
SOURCE_RUN2 = HERE / "xlsx_synthetic" / "source_files_run2"
CONFIG = HERE / "config_synthetic"
CONFIG_RUN2 = HERE / "config_synthetic_run2"
FIXED_TIME = datetime(2026, 1, 1)

HEADER = ["Item No.", "Item Description", "Estimated Quantity", "Units"]


def _new_workbook() -> Workbook:
    wb = Workbook()
    wb.properties.created = FIXED_TIME
    wb.properties.modified = FIXED_TIME
    wb.properties.creator = "synthetic fixture"
    return wb


def _bid_sheet(ws, header_lines, bidder_row, header_row, items):
    """Write a bid tab: header lines from A1, bidder names, table header, item rows."""
    for r, values in enumerate(header_lines, start=1):
        for c, v in enumerate(values, start=1):
            if v is not None:
                ws.cell(row=r, column=c, value=v)
    bidder_r = len(header_lines) + 2
    for c, v in bidder_row.items():
        ws.cell(row=bidder_r, column=c, value=v)
    header_r = bidder_r + 1
    for c, v in enumerate(header_row, start=1):
        ws.cell(row=header_r, column=c, value=v)
    for offset, item in enumerate(items, start=1):
        number_format = None
        if isinstance(item, tuple) and len(item) == 2 and isinstance(item[1], dict):
            item, opts = item
            number_format = opts.get("item_no_format")
        for c, v in enumerate(item, start=1):
            if v is not None:
                ws.cell(row=header_r + offset, column=c, value=v)
        if number_format:
            ws.cell(row=header_r + offset, column=1).number_format = number_format


def _three_bidder_header():
    return HEADER + ["Unit Price", "Total Price"] * 3


def _three_bidder_names():
    # Covers all three bidder-name branches in 01 detect_bidder_blocks:
    #   E/F: name in the unit-price column only    -> Engineer's Estimate
    #   G/H: same name in both columns             -> ACME
    #   I/J: name in the total-price column only   -> Beta
    return {5: "Engineer's Estimate", 7: "ACME PAVING, INC.", 8: "ACME PAVING, INC.", 10: "Beta Builders LLC"}


def build_syn_a() -> None:
    """Two canonical sheets, EE bidder, section header, #REF!, totals, '0', hyphenated item."""
    wb = _new_workbook()
    base = wb.active
    base.title = "Base Bid Tab"
    header_lines = [
        ["PORTLAND INTERNATIONALAIRPORT"],  # 02 inserts the space before AIRPORT
        ["SYNTHETIC TAXIWAY REHAB"],
        ["EAN 2099D001"],
        ["Solicitation No. 2099-00001"],
        ["Bid Opening: 03/05/2024"],
    ]
    _bid_sheet(
        base,
        header_lines,
        _three_bidder_names(),
        _three_bidder_header(),
        [
            [None, "GENERAL"],  # section header: no item no, not emitted by 01
            ([1, "Mobilization", 1, "LS", 50000, 50000, 48000, 48000, 52000, 52000], {"item_no_format": "000"}),
            [2, 'Asphalt Pavement, 4" Thick', 1200, "SY", 25.5, 30600, 24, 28800, "#REF!", "#REF!"],
            ["3-A", "Crushed  Aggregate Base Course", 300, "C.Y.", 40, 12000, 38.75, 11625, 41, 12300],
            [4, "#REF!", 1, "EA", 1, 1, 1, 1, 1, 1],  # dropped in 02
            [5, "0", 1, "EA", 1, 1, 1, 1, 1, 1],  # dropped in 02
            [6, "Traffic Control", 1, "Lump Sum", 0, 0, 5000, 5000, None, None],
            [None, "TOTAL AMOUNT BID", None, None, None, 92600, None, 93425, None, 64300],
        ],
    )
    alt = wb.create_sheet("Alternate Bid Tab 1")
    _bid_sheet(
        alt,
        header_lines,
        _three_bidder_names(),
        _three_bidder_header(),
        [
            [1, 'Electrical Conduit 2"', 500, "LF", 12, 6000, 11, 5500, 13, 6500],
            [2, "Unmapped Widget", 3, "EA", 100, 300, 90, 270, 95, 285],
            [None, "Basis of Award: Base plus Alternate 1"],  # totals pattern
        ],
    )
    wb.save(SOURCE / "SYN_A Bid Tab.xlsx")


def build_syn_b() -> None:
    """Sheet name needs case-insensitive match; awarded via raw name; empty canonical sheet."""
    wb = _new_workbook()
    base = wb.active
    base.title = "base bid tab "  # 01 matches sheet names case-insensitively after strip
    _bid_sheet(
        base,
        [
            ["HILLSBOROAIRPORT"],
            ["SYNTHETIC APRON LIGHTING"],
            ["EAN 2099D002"],
            ["Solicitation No.: 2099-00002 | Rebid"],
            ["Bid Date", datetime(2024, 6, 12)],
        ],
        {5: "Gamma Construction", 6: "Gamma Construction", 7: "Acme Paving Inc", 8: "Acme Paving Inc"},
        ["Item No", "Item Description", "Estimated Quantity", "Units"] + ["Unit Price", "Total Price"] * 2,
        [
            [1, "MOBILIZATION ", 1, "L.S.", 8000, 8000, 9000, 9000],
            [2, "WORKZONE TRAFFICCONTROL", 1, "Each", 1500, 1500, 1400, 1400],
            [3, "Light Fixture, Type A", 12, "each", 900, 10800, 950, 11400],
            [4, "Spare Parts Allowance", 1, "LS", None, 2500, None, 2500],
        ],
    )
    empty = wb.create_sheet("Alternate Bid Tab 2")  # no table header: 01 warns and skips
    empty["A1"] = "No alternates were bid."
    wb.create_sheet("Notes")  # not canonical: ignored
    wb.save(SOURCE / "SYN_B.xlsx")


def build_syn_c() -> None:
    """Second-run newcomer. No awarded match, so projects_with_awarded < projects."""
    wb = _new_workbook()
    base = wb.active
    base.title = "Base Bid Tab"
    _bid_sheet(
        base,
        [
            ["TROUTDALE AIRPORT"],
            ["SYNTHETIC HANGAR ACCESS ROAD"],
            ["EAN 2099D003"],
            ["Solicitation No. 2099-00003"],
            ["Bid Opening: Sep 9, 2025"],
        ],
        {5: "Delta Paving Co", 6: "Delta Paving Co", 7: "Engineers Estimate", 8: "Engineers Estimate"},
        HEADER + ["Unit Price", "Total Price"] * 2,
        [
            [1, "Mobilization", 1, "LS", 20000, 20000, 18000, 18000],
            [2, "Unmapped Gate Operator", 2, "EA", 7000, 14000, 6500, 13000],
        ],
    )
    wb.save(SOURCE / "SYN_C.xlsx")


def build_syn_d() -> None:
    """Alternate-only workbook. Text prices and quantities, an unpaired Unit Price column, a stray row after a gap."""
    wb = _new_workbook()
    alt = wb.active
    alt.title = "Alternate Bid Tab"  # no Base Bid Tab sheet
    _bid_sheet(
        alt,
        [
            ["PORTLAND INTERNATIONAL AIRPORT"],
            ["SYNTHETIC CANOPY ALTERNATE"],
            ["EAN 2099D004"],
            ["Solicitation No. 2099-00004"],
            ["Bid Opening: 2025-01-15"],
        ],
        {5: "Delta Paving Co", 6: "Delta Paving Co", 7: "Beta Builders LLC", 8: "Beta Builders LLC"},
        # Third Unit Price has no Total Price partner: 01 warns bidder_pair_count_mismatch and ignores it.
        HEADER + ["Unit Price", "Total Price", "Unit Price", "Total Price", "Unit Price"],
        [
            [1, "Mobilization", 1, "LS", "$1,250.00", "$1,250.00", "1,300", "1,300", 5],
            [2, "Canopy Steel", "1,200", "LB", "-", 6000, "TBD", "TBD", 5],  # dash and text prices: null
            [3, "Credit For Salvage", 1, "LS", "(100)", "(100)", "(150.50)", "(150.50)", 5],  # negatives
            *[[None] * 9 for _ in range(10)],  # ten blank rows end the table
            [99, "Stray Row After Gap", 1, "EA", 1, 1, 1, 1, 1],  # never read
        ],
    )
    wb.save(SOURCE / "SYN_D.xlsx")


def _two_bidder_book(path: Path, ean: str, sol: str, project: str, bidders: list[str], items: list[list]) -> None:
    wb = _new_workbook()
    ws = wb.active
    ws.title = "Base Bid Tab"
    names = {}
    for i, name in enumerate(bidders):
        names[5 + 2 * i] = name
        names[6 + 2 * i] = name
    _bid_sheet(
        ws,
        [["PORTLAND INTERNATIONAL AIRPORT"], [project], [f"EAN {ean}"], [f"Solicitation No. {sol}"], ["06/01/2025"]],
        names,
        HEADER + ["Unit Price", "Total Price"] * len(bidders),
        items,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def build_delta_report_books() -> None:
    """Workbooks that persist into the second run with one controlled change each."""
    e_items = [
        [1, "Mobilization", 1, "LS", 3000, 3000, 3100, 3100],
        [2, "Traffic Control", 4, "LS", 0, 0, 900, 3600],  # contractor total 0 with quantity 4: suspicious
    ]
    _two_bidder_book(
        SOURCE / "SYN_E.xlsx", "2099D005", "2099-00005", "SYNTHETIC E ROWS", ["Echo Co", "Foxtrot Co"], e_items
    )
    _two_bidder_book(
        SOURCE_RUN2 / "SYN_E.xlsx",
        "2099D005",
        "2099-00005",
        "SYNTHETIC E ROWS",
        ["Echo Co", "Foxtrot Co"],
        e_items + [[3, "Light Fixture, Type A", 2, "EA", 500, 1000, 450, 900]],  # one more item: rows change
    )
    # 01 needs at least two bidders to detect a table, so the bidder count changes 3 -> 2
    # while rows stay at 6 (3 bidders x 2 items, then 2 bidders x 3 items).
    f_mapped = ["Mobilization", "Traffic Control", "Light Fixture, Type A"]
    _two_bidder_book(
        SOURCE / "SYN_F.xlsx",
        "2099D006",
        "2099-00006",
        "SYNTHETIC F BIDDERS",
        ["Golf Co", "Hotel Co", "Lima Co"],
        [[i + 1, d, 1, "LS", 100, 100, 110, 110, 120, 120] for i, d in enumerate(f_mapped[:2])],
    )
    _two_bidder_book(
        SOURCE_RUN2 / "SYN_F.xlsx",
        "2099D006",
        "2099-00006",
        "SYNTHETIC F BIDDERS",
        ["Golf Co", "Hotel Co"],
        [[i + 1, d, 1, "LS", 100, 100, 110, 110] for i, d in enumerate(f_mapped)],
    )
    _two_bidder_book(
        SOURCE / "SYN_G.xlsx",
        "2099D007",
        "2099-00007",
        "SYNTHETIC G AWARD",
        ["India Co", "Juliet Co"],
        [[1, "Mobilization", 1, "LS", 700, 700, 650, 650]],
    )
    _two_bidder_book(
        SOURCE / "SYN_H.xlsx",
        "2099D008",
        "2099-00008",
        "SYNTHETIC H UNMAPPED",
        ["Kilo Co", "Mike Co"],
        [[1, "Hangar Door Seal", 10, "LF", 20, 200, 22, 220], [2, "Mobilization", 1, "LS", 900, 900, 950, 950]],
    )


def build_simple(path: Path, sheet_title: str) -> None:
    """A minimal valid workbook, used where the file must be skipped by name or location."""
    wb = _new_workbook()
    ws = wb.active
    ws.title = sheet_title
    _bid_sheet(
        ws,
        [["SKIPPED AIRPORT"], ["SHOULD NOT APPEAR"], ["EAN 2099D999"], ["Solicitation No. 2099-99999"], ["01/01/2020"]],
        {5: "Nobody Inc", 6: "Nobody Inc"},
        HEADER + ["Unit Price", "Total Price"],
        [[1, "Should Not Appear", 1, "LS", 1, 1]],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def build_awarded_bids(folder: Path, syn_g_awardee: str) -> None:
    """02 reads this with header=4: four junk rows, then the header on row 5."""
    wb = _new_workbook()
    ws = wb.active
    ws.title = "Awarded Bids"
    ws["A1"] = "Awarded Bids Search List (synthetic)"
    ws["A3"] = "Generated for tests"
    for c, v in enumerate(["Invitation #", "Project", "Bidder", "Award Amount"], start=1):
        ws.cell(row=5, column=c, value=v)
    rows = [
        ["2099-00001", "Synthetic Taxiway", '"Acme  Paving, Inc."', 1234567.0],  # quotes and double space
        ["2099-00001", "Synthetic Taxiway", "Beta Builders LLC", None],  # no amount: filtered out
        ["2099-00002", "Synthetic Apron", "GAMMA CONSTRUCTION", 99000.0],
        ["2099-00002", "Synthetic Apron", "Gamma Construction", 99000.0],  # duplicate after cleaning
        ["2099-77777", "Other Project", "Nobody Inc", 5.0],  # matches no bid tab
        ["2099-00007", "Synthetic G", syn_g_awardee, 700.0],  # changes between runs
    ]
    for r, row in enumerate(rows, start=6):
        for c, v in enumerate(row, start=1):
            if v is not None:
                ws.cell(row=r, column=c, value=v)
    folder.mkdir(parents=True, exist_ok=True)
    wb.save(folder / "AwardedBidsSearchList.xlsx")


def main() -> None:
    SOURCE.mkdir(parents=True, exist_ok=True)
    build_syn_a()
    build_syn_b()
    build_syn_c()
    build_syn_d()
    build_delta_report_books()
    build_simple(SOURCE / "PDX_2017D013.xlsx", "Base Bid Tab")  # in 01 SKIP_FILES
    build_simple(SOURCE / "archive" / "SYN_OLD.xlsx", "Base Bid Tab")  # subfolder: not listed
    wb = _new_workbook()
    wb.active.title = "Summary"
    wb.save(SOURCE / "SYN_NOSHEETS.xlsx")  # no canonical sheet names
    (SOURCE / "SYN_CORRUPT.xlsx").write_bytes(b"not a zip archive\n")  # openpyxl raises: errored file
    (SOURCE / "~$SYN_A Bid Tab.xlsx").write_bytes(b"\x00office lock file\n")  # skipped by name
    (SOURCE / "notes.txt").write_text("Not a workbook.\n")
    build_awarded_bids(CONFIG, "India Co")
    build_awarded_bids(CONFIG_RUN2, "Juliet Co")


if __name__ == "__main__":
    main()
