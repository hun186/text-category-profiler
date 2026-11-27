"""Bounded offline article text review; no file or network operations."""
from __future__ import annotations

import hashlib
from itertools import combinations
import unicodedata


def normalize_article_text(body: bytes | bytearray) -> str:
    """Decode strict UTF-8 text with NFC and Unicode whitespace normalization.

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
    return normalized


def review_text_fingerprint(body: bytes | bytearray) -> str:
    """Preserve the original normalized content fingerprint contract."""
    return hashlib.sha256(normalize_article_text(body).encode("utf-8")).hexdigest()


def normalized_duplicate_groups(fingerprints: dict[str, str]) -> list[list[str]]:
    """Deterministic source groups; never expose text or delete candidates."""
    by_hash: dict[str, list[str]] = {}
    for source, fingerprint in fingerprints.items():
        by_hash.setdefault(fingerprint, []).append(source)
    return sorted(sorted(group) for group in by_hash.values() if len(group) > 1)

# Explicit first-version resource and evidence limits, not calibrated quality
# thresholds. No sampling or truncation: refuse over-budget evidence.
MAX_NEAR_ARTICLES = 100
MAX_NEAR_ARTICLE_CHARS = 50_000
MAX_NEAR_TOTAL_CHARS = 500_000
MIN_NEAR_CHARS = 100
MIN_NEAR_SHINGLES = 20
SHINGLE_WIDTH = 5


def character_shingles(text: str) -> set[str]:
    """Contiguous normalized character 5-grams, suitable for CJK too."""
    if len(text) > MAX_NEAR_ARTICLE_CHARS:
        raise ValueError("near-duplicate article exceeds normalized character budget")
    if len(text) < MIN_NEAR_CHARS:
        return set()
    shingles = {text[i:i + SHINGLE_WIDTH]
                for i in range(len(text) - SHINGLE_WIDTH + 1)}
    return shingles if len(shingles) >= MIN_NEAR_SHINGLES else set()


def near_duplicate_pairs(fingerprints: dict[str, str],
                         shingles_by_source: dict[str, set[str]]) -> list[dict]:
    """Return lexical Jaccard >= 4/5 pairs; exact normalized groups are separate.

    Inputs must come from bounded, already verified and normalized articles.
    Short/repetitive documents are excluded by the caller and reported.
    No semantic judgment, clustering, source approval or file mutation.
    """
    pairs = []
    for left, right in combinations(sorted(shingles_by_source), 2):
        if fingerprints[left] == fingerprints[right]:
            continue
        a, b = shingles_by_source[left], shingles_by_source[right]
        if not a or not b:
            continue
        # Upper bound on Jaccard from set sizes; avoid unnecessary intersections.
        if 5 * min(len(a), len(b)) < 4 * max(len(a), len(b)):
            continue
        shared = len(a & b)
        union = len(a) + len(b) - shared
        if 5 * shared >= 4 * union:
            pairs.append({
                "Sources": [left, right],
                "Jaccard": round(shared / union, 6),
                "SharedShingles": shared,
                "UnionShingles": union,
            })
    return sorted(pairs, key=lambda pair: (-pair["Jaccard"], pair["Sources"]))
