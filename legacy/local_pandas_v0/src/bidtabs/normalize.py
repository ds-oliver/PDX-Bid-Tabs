from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\.,;:]+$")
_SUFFIX_FIXES = {
    "INC": "INC.",
    "CO": "CO.",
    "CORP": "CORP.",
    "LLC": "LLC",
    "LTD": "LTD.",
}


def clean_whitespace(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    return _WS_RE.sub(" ", text)


def _load_name_map(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    df = pd.read_csv(p)
    if not {"raw_name", "canonical_name"}.issubset(df.columns):
        return {}
    return {
        clean_whitespace(raw).upper(): clean_whitespace(canon)
        for raw, canon in zip(df["raw_name"], df["canonical_name"])
        if clean_whitespace(raw)
    }


def canonicalize_name(value: object, name_map: Optional[Dict[str, str]] = None) -> str:
    text = clean_whitespace(value)
    if not text:
        return ""
    key = text.upper()
    if name_map and key in name_map:
        return name_map[key]

    tokens = []
    for tok in key.split(" "):
        tok = _PUNCT_RE.sub("", tok)
        tok = _SUFFIX_FIXES.get(tok, tok)
        tokens.append(tok)
    return " ".join(tokens)


def normalize_unit_code(value: object) -> str:
    text = clean_whitespace(value).upper().replace(" ", "")
    return text


def parse_decimal(value: object) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = clean_whitespace(value)
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    if text in {"", "-", "--"}:
        return None
    try:
        dec = Decimal(text)
    except InvalidOperation:
        return None
    return -dec if negative else dec


def parse_float(value: object):
    dec = parse_decimal(value)
    return float(dec) if dec is not None else None


def load_name_map(config_dir: str) -> Dict[str, str]:
    return _load_name_map(str(Path(config_dir) / "contractor_name_map.csv"))
