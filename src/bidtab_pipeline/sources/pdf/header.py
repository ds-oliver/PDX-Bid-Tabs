"""Header block (FR-10): airport, project name, EAN, solicitation number, bid date.

The block is the top-left cell of every page:

    PORTLAND INTERNATIONAL AIRPORT          <- location (first line)
    TAXIWAY K REHABILITATION                <- project name (one or more lines)
    EAN 2017D013
    Solicitation No. 2018-7876
    1/22/2019
"""

from __future__ import annotations

import re
from datetime import datetime

from bidtab_pipeline.sources.pdf.model import HeaderBlock, LayoutFlag
from bidtab_pipeline.sources.pdf.tables import cell_lines

_EAN = re.compile(r"EAN\s+(\S+)")
_SOLICITATION = re.compile(r"Solicitation No\.\s*(\S+)")
_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")


def parse_header_block(text: str | None, page_no: int | None = None) -> HeaderBlock:
    lines = cell_lines(text)

    def find(pattern: re.Pattern) -> int | None:
        return next((i for i, ln in enumerate(lines) if pattern.fullmatch(ln)), None)

    i_ean, i_sol, i_date = find(_EAN), find(_SOLICITATION), find(_DATE)
    if i_ean is None or i_sol is None or i_date is None or not (2 <= i_ean < i_sol < i_date):
        raise LayoutFlag(
            "header_block_unrecognized",
            f"expected location, project name, 'EAN …', 'Solicitation No. …', and a m/d/yyyy date, got {lines!r}",
            page_no,
        )
    bid_date_raw = lines[i_date]
    return HeaderBlock(
        location_raw=lines[0],
        project_name_raw=" ".join(lines[1:i_ean]),
        ean=_EAN.fullmatch(lines[i_ean]).group(1),
        solicitation_no=_SOLICITATION.fullmatch(lines[i_sol]).group(1),
        bid_date_raw=bid_date_raw,
        bid_date=datetime.strptime(bid_date_raw, "%m/%d/%Y").date(),
    )
