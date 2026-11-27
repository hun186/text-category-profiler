"""Bounded offline article text review; no file or network operations."""
from __future__ import annotations

import hashlib
import unicodedata


def review_text_fingerprint(body: bytes | bytearray) -> str:
    """Hash strict UTF-8 text after NFC and Unicode whitespace normalization.

    This is exact normalized equality, not semantic or near-duplicate search.
    Keep case and punctuation. Reject blank text and NUL-bearing input.
    The caller owns byte budgets and verifies original byte integrity.
    """
    try:
        text = body.decode("utf-8-sig", errors="strict")
    except UnicodeError as exc:
        raise ValueError("article is not valid UTF-8 text") from exc
    if "\x00" in text:
        raise ValueError("article text contains NUL")
    normalized = " ".join(unicodedata.normalize("NFC", text).split())
    if not normalized:
        raise ValueError("article text is blank")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalized_duplicate_groups(fingerprints: dict[str, str]) -> list[list[str]]:
    """Deterministic source groups; never expose text or delete candidates."""
    by_hash: dict[str, list[str]] = {}
    for source, fingerprint in fingerprints.items():
        by_hash.setdefault(fingerprint, []).append(source)
    return sorted(sorted(group) for group in by_hash.values() if len(group) > 1)
