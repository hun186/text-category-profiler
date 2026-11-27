"""Explicit, bounded lexical review of candidate-specific article evidence.

No network, file writes, source verification or automatic classification.
"""
from __future__ import annotations

import unicodedata

MAX_RELEVANCE_CANDIDATES = 100
MAX_GROUPS = 8
MAX_ALIASES = 8
MAX_ALIAS_CHARS = 120
MAX_EVALUATED_CHARS = 500_000
MAX_RELEVANCE_ARTICLE_CHARS = 50_000


def normalize_literal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def validate_relevance_rules(manifest: object, labels: set[str]) -> dict:
    """Require one explicit rule per candidate; reject ambiguous specifications."""
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "rules"}:
        raise ValueError("relevance rules require schema_version and rules")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ValueError("invalid relevance rules schema version")
    raw = manifest["rules"]
    if not isinstance(raw, dict) or set(raw) != labels or not (
        1 <= len(raw) <= MAX_RELEVANCE_CANDIDATES
    ):
        raise ValueError("relevance rule labels must match all candidate labels exactly")
    rules = {}
    for label, rule in sorted(raw.items()):
        if not isinstance(rule, dict) or set(rule) != {"groups", "min_groups"}:
            raise ValueError(f"{label!r}: expected groups/min_groups")
        groups, minimum = rule["groups"], rule["min_groups"]
        if not isinstance(groups, list) or not 1 <= len(groups) <= MAX_GROUPS:
            raise ValueError(f"{label!r}: invalid group count")
        if type(minimum) is not int or not 1 <= minimum <= len(groups):
            raise ValueError(f"{label!r}: invalid min_groups")
        normalized = []
        seen = set()
        for group in groups:
            if not isinstance(group, list) or not 1 <= len(group) <= MAX_ALIASES:
                raise ValueError(f"{label!r}: invalid alias count")
            aliases = []
            for alias in group:
                if not isinstance(alias, str) or len(alias) > MAX_ALIAS_CHARS or "\x00" in alias:
                    raise ValueError(f"{label!r}: invalid alias")
                value = normalize_literal(alias)
                if not value or len(value) > MAX_ALIAS_CHARS or value in seen:
                    raise ValueError(f"{label!r}: blank or repeated normalized alias")
                seen.add(value)
                aliases.append(value)
            normalized.append(tuple(aliases))
        rules[label] = (tuple(normalized), minimum)
    return rules


def evaluate_relevance(label: str, source: str, normalized_text: str, rule: tuple) -> dict:
    """Report literal substring hits per OR group; never approve relevance."""
    groups, minimum = rule
    text = normalize_literal(normalized_text)
    hits = []
    for index, group in enumerate(groups, 1):
        matched = [alias for alias in group if alias in text]
        hits.append({"Group": index, "MatchedAliases": matched})
    count = sum(bool(item["MatchedAliases"]) for item in hits)
    return {
        "ClassLabel": label,
        "Source": source,
        "NormalizedCharacterCount": len(normalized_text),
        "ShortArticle": len(normalized_text) < 100,
        "MatchedGroups": count,
        "RequiredGroups": minimum,
        "TotalGroups": len(groups),
        "GroupMatches": hits,
        "Status": "LEXICAL_THRESHOLD_MET" if count >= minimum else "REVIEW_REQUIRED",
    }
