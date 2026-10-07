"""Silver config files: port of reference notebook 02's config loads.

Logic is unchanged from 02, statement for statement. Note that unit_mapping.csv
is loaded but no query reads it (docs/backlog.md B-05); it is still loaded so a
missing or unreadable file fails the job exactly as before.
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
