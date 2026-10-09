"""Silver config files: port of reference notebook 02's config loads.

Logic is unchanged from 02, statement for statement. Note that unit_mapping.csv
is loaded but no query reads it (docs/backlog.md B-05); it is still loaded so a
missing or unreadable file fails the job exactly as before.

One deliberate change from 02 (backlog B-14, branch fix/b14-bid-date, pending Port
sign-off): load_due_dates reads the Due Date column of AwardedBidsSearchList.xlsx so
Silver can replace the workbook bid date, which is a cached =TODAY().
"""

from __future__ import annotations

import re

import pandas as pd

CONTRACTOR_MAPPING_FILE = "contractor_alias_mapping.csv"
AWARDED_BIDS_FILE = "AwardedBidsSearchList.xlsx"
CONCAT_FIXES_FILE = "concat_fixes.csv"
TEXT_NORMALIZATION_FILE = "text_normalization.csv"
UNIT_MAPPING_FILE = "unit_mapping.csv"


def load_contractor_aliases(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def load_unit_mapping(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def load_awarded_bids(awarded_bids_path: str, contractor_mapping_path: str) -> pd.DataFrame:
    """Awarded bids with canonical bidder names, one row per (invitation_no, bidder)."""
    _awarded_pdf = pd.read_excel(awarded_bids_path, header=4)

    _awarded_pdf = _awarded_pdf[
        _awarded_pdf["Award Amount"].notna() & _awarded_pdf["Invitation #"].notna() & _awarded_pdf["Bidder"].notna()
    ].copy()

    _awarded_pdf["invitation_no"] = _awarded_pdf["Invitation #"].astype(str).str.strip()
    _awarded_pdf["award_amount"] = _awarded_pdf["Award Amount"]

    _awarded_pdf["awarded_bidder_clean"] = (
        _awarded_pdf["Bidder"]
        .astype(str)
        .str.replace('"', "", regex=False)
        .str.upper()
        .str.strip()
        .str.replace(r"\s+", " ", regex=True)
    )

    _contractor_alias_pdf = pd.read_csv(contractor_mapping_path)
    _alias_dict = dict(
        zip(
            _contractor_alias_pdf["contractor_name_clean"],
            _contractor_alias_pdf["contractor_name_canonical"],
            strict=False,
        )
    )
    _awarded_pdf["awarded_bidder_canonical"] = (
        _awarded_pdf["awarded_bidder_clean"].map(_alias_dict).fillna(_awarded_pdf["awarded_bidder_clean"])
    )

    # Keep award_amount so Silver join can filter on it
    return _awarded_pdf[["invitation_no", "awarded_bidder_canonical", "award_amount"]].drop_duplicates(
        subset=["invitation_no", "awarded_bidder_canonical"]
    )


DUE_DATE_FORMAT = "%m/%d/%Y %I:%M:%S %p"  # PlanetBids export, e.g. "08/09/2024 3:00:00 PM"


def load_due_dates(awarded_bids_path: str) -> pd.DataFrame:
    """One bid due date per solicitation from AwardedBidsSearchList.xlsx (B-14).

    The export repeats the Due Date on every bidder row. Every row counts, not only
    awarded ones. Unparseable or blank values are dropped. Where a solicitation has
    more than one Due Date (2 of 700 in the 2026-05-23 export, both re-bid or extended),
    the latest is used. A file without a Due Date column yields no rows, so Silver keeps
    the workbook date.
    """
    df = pd.read_excel(awarded_bids_path, header=4)
    if "Due Date" not in df.columns or "Invitation #" not in df.columns:
        return pd.DataFrame({"invitation_no": pd.Series(dtype=str), "due_date": pd.Series(dtype=object)})
    df = df[df["Invitation #"].notna()].copy()
    due = pd.to_datetime(df["Due Date"].astype(str).str.strip(), format=DUE_DATE_FORMAT, errors="coerce")
    out = pd.DataFrame({"invitation_no": df["Invitation #"].astype(str).str.strip(), "due_date": due})
    out = out.dropna(subset=["due_date"]).groupby("invitation_no", as_index=False)["due_date"].max()
    out["due_date"] = out["due_date"].dt.date
    return out


def load_concat_fixes(path: str) -> list[tuple[str, str]]:
    _concat_pdf = pd.read_csv(path)
    return list(zip(_concat_pdf["pattern"], _concat_pdf["replacement"], strict=False))


def load_text_normalizations(path: str) -> list[tuple[str, str]]:
    """Anchored full-string regex aliases (^FROM$ -> TO) that fold cosmetic variants to a canonical form.

    Read with keep_default_na=False so an empty replacement stays "" and "NA" stays text.
    """
    _textnorm_pdf = pd.read_csv(path, keep_default_na=False)
    return list(zip(_textnorm_pdf["pattern"], _textnorm_pdf["replacement"], strict=False))


def make_normalize_description(CONCAT_FIXES, TEXT_NORMALIZATIONS):  # noqa: N803 - names kept from 02
    """Build 02's normalize_description over the loaded config. The body is unchanged from 02."""

    def normalize_description(desc):
        """Apply non-destructive spacing fixes to a pay item description."""
        if desc is None:
            return None
        cleaned = desc.strip()
        for pattern, replacement in CONCAT_FIXES:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'(\d)"', r"\1-INCH", cleaned)
        cleaned = re.sub(r"(\d)'", r"\1-FOOT", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        for pattern, replacement in TEXT_NORMALIZATIONS:
            cleaned = re.sub(pattern, replacement, cleaned)
        return cleaned

    return normalize_description
