from __future__ import annotations

import hashlib
from typing import Iterable


def stable_hash_int(parts: Iterable[object], digits: int = 12) -> int:
    text = "||".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return int(digest[:digits], 16)
