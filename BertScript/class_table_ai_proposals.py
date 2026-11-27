"""Read-only provenance gate for AI-generated ClassTable candidate CSVs.

This module never writes the authoritative ClassTable or TopicTree. Passing
validation only means proposal metadata is well-formed, NOT that any taxonomy
change has been approved or that source evidence has been independently checked.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
from datetime import date
from itertools import chain
import json
from pathlib import Path
import re

from BertScript.article_text_review import (
    normalize_article_text, normalized_duplicate_groups, character_shingles,
    near_duplicate_pairs, MAX_NEAR_ARTICLES, MAX_NEAR_TOTAL_CHARS,
)

from BertScript.class_table_metadata import (
    DEFAULT_CSV,
    MetadataError,
    load_class_table,
    topic_nodes,
)

NOTE_KINDS = ("AI新增", "AI補充")
NOTE_FIELDS = ("日期", "來源", "理由", "狀態")
PENDING_REVIEW = "待人工審核"


def parse_provenance(note: str, label: str) -> tuple[str, dict[str, str]]:
    """Parse the documented Notes format without accepting fake approvals."""
    parts = note.split("｜")
    if len(parts) != 5 or parts[0] not in NOTE_KINDS:
        raise MetadataError(
            f"{label!r}: Notes must start with AI新增 or AI補充 and contain "
            "日期｜來源｜理由｜狀態"
        )
    fields: dict[str, str] = {}
    for expected, part in zip(NOTE_FIELDS, parts[1:]):
        key, separator, value = part.partition("=")
        if not separator or key != expected or not value.strip():
            raise MetadataError(f"{label!r}: invalid or missing Notes field {expected}")
        fields[key] = value.strip()
    try:
        parsed = date.fromisoformat(fields["日期"])
    except ValueError as exc:
        raise MetadataError(f"{label!r}: 日期 must be YYYY-MM-DD") from exc
    if parsed.isoformat() != fields["日期"]:
        raise MetadataError(f"{label!r}: 日期 must be YYYY-MM-DD")
    if fields["狀態"] != PENDING_REVIEW:
        raise MetadataError(
            f"{label!r}: AI proposal must remain {PENDING_REVIEW}; "
            "a Notes value is not an approval"
        )
    return parts[0], fields


def audit_proposals(
    base: dict[str, dict[str, str]],
    candidates: dict[str, dict[str, str]],
) -> dict[str, object]:
    """Check provenance and prohibit overwriting the existing Chinese name.

    Proposed Explanation text for an existing label is permitted for human
    review, but is never merged or persisted by this read-only function.
    """
    additions: list[str] = []
    supplements: list[str] = []
    for label in sorted(candidates):
        proposed = candidates[label]
        kind, _ = parse_provenance(proposed.get("Notes", ""), label)
        existing = base.get(label)
        if kind == "AI新增":
            if existing is not None:
                raise MetadataError(
                    f"{label!r}: AI新增 conflicts with existing ClassTable metadata"
                )
            additions.append(label)
        else:
            if existing is None:
                raise MetadataError(
                    f"{label!r}: AI補充 requires an existing ClassLabel"
                )
            if proposed["CT"] != existing["CT"]:
                raise MetadataError(
                    f"{label!r}: AI補充 must preserve the human CT; "
                    "submit an explicit manual change instead"
                )
            supplements.append(label)
    return {
        "CandidateCount": len(candidates),
        "AI新增": additions,
        "AI補充": supplements,
        "Status": PENDING_REVIEW,
        "Approved": False,
        "AuthoritativeFilesModified": False,
    }



def _read_edge_rows(path: str | Path) -> list[tuple[str, str, str]]:
    """Read edge identities (parent, child, relation); date/notes are not identity.

    This is a bounded structural preflight, not semantic validation. Relation
    types other than literal 'contains' may intentionally be non-hierarchical.
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            first = next(reader, None)
            if first is None:
                raise MetadataError(f"{path}: empty TopicTree")
            names = [cell.strip().lstrip("#").casefold() for cell in first[:2]]
            has_header = (
                len(names) >= 2
                and (
                    ("母類別" in names[0] and "子類別" in names[1])
                    or names in (["parent", "child"], ["source", "target"])
                )
            )
            rows = reader if has_header else chain((first,), reader)
            result: list[tuple[str, str, str]] = []
            for row_number, row in enumerate(rows, 2 if has_header else 1):
                if len(row) < 2 or not row[0] or not row[1]:
                    raise MetadataError(
                        f"{path}: missing edge endpoint near row {row_number}"
                    )
                result.append((row[0], row[1], row[3] if len(row) > 3 else ""))
            return result
    except (csv.Error, UnicodeError) as exc:
        raise MetadataError(f"{path}: invalid graph CSV: {exc}") from exc


def _audit_new_edge_structure(
    base_tree: str | Path, proposed_edges: str | Path
) -> int:
    """Reject repeated/self relations and newly formed literal contains cycles.

    Existing graph anomalies are not retroactively rejected. This does NOT
    approve relationship semantics or assume non-'contains' relations are DAGs.
    """
    original = _read_edge_rows(base_tree)
    proposed = _read_edge_rows(proposed_edges)
    known = set(original)
    for edge in proposed:
        if edge[0] == edge[1]:
            raise MetadataError(f"proposed self-edge: {edge!r}")
        if edge in known:
            raise MetadataError(f"duplicate proposed graph relation: {edge!r}")
        known.add(edge)

    adjacency: dict[str, set[str]] = {}
    for parent, child, relation in [*original, *proposed]:
        if relation.strip().casefold() == "contains":
            adjacency.setdefault(parent, set()).add(child)
    for parent, child, relation in proposed:
        if relation.strip().casefold() != "contains":
            continue
        stack = [child]
        visited: set[str] = set()
        while stack:
            node = stack.pop()
            if node == parent:
                raise MetadataError(
                    f"proposed 'contains' cycle via {parent!r} -> {child!r}"
                )
            if node not in visited:
                visited.add(node)
                stack.extend(adjacency.get(node, ()))
    return len(proposed)


def audit_proposed_graph_nodes(
    additions: list[str],
    *,
    base_tree: str | Path,
    proposed_edges: str | Path,
) -> dict[str, object]:
    """Match proposed new graph node identities to AI新增 labels only.

    Graph relationship semantics, article evidence and authorization remain
    unchecked. Exact duplicate/self edges and cycles of literal 'contains'
    relations introduced by proposed edges are rejected. This never reads/writes official
    metadata output files; only the two supplied graph CSVs are read.
    """
    original = topic_nodes(base_tree)
    added = topic_nodes(proposed_edges) - original
    expected = set(additions)
    missing_in_edges = sorted(expected - added)
    missing_in_candidates = sorted(added - expected)
    if missing_in_edges or missing_in_candidates:
        raise MetadataError(
            "AI additions / proposed edge-node mismatch: "
            f"missing_in_edges={missing_in_edges}, "
            f"missing_in_candidates={missing_in_candidates}"
        )
    checked_edges = _audit_new_edge_structure(base_tree, proposed_edges)
    return {
        "GraphNodeAlignment": "matched",
        "NewGraphNodes": sorted(added),
        "ProposedEdgesStructurallyChecked": checked_edges,
        "GraphRelationshipsApproved": False,
    }



MAX_EVIDENCE_ARTICLES = 1000
MAX_ARTICLE_BYTES = 10_000_000
SHA256_PATTERN = re.compile("[0-9a-f]{64}")


def _unique_evidence_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys at every nesting level before auditing.

    json.loads normally keeps only the final value for repeated keys, which
    can hide a conflicting articles collection or article source binding.
    """
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def audit_local_article_evidence(
    candidates: dict[str, dict[str, str]], manifest_path: str | Path, *,
    review_text: bool = False, review_near_duplicates: bool = False,
) -> dict[str, object]:
    """Verify local file integrity and exact source bindings, without fetching.

    Source identity is an opaque exact Notes value: no URL authenticity or
    document semantic relevance is inferred. The manifest directory is the
    permitted file boundary, including after symlink resolution.
    """
    if review_near_duplicates and not review_text:
        raise MetadataError("near-duplicate review requires text review")
    manifest_path = Path(manifest_path)
    try:
        manifest = json.loads(
            manifest_path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=_unique_evidence_json_object,
        )
    except (UnicodeError, ValueError) as exc:
        raise MetadataError(f"invalid JSON evidence manifest: {exc}") from exc
    if not isinstance(manifest, dict) or set(manifest) != {"schema_version", "articles"}:
        raise MetadataError("evidence manifest requires schema_version and articles")
    records = manifest["articles"]
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1 or not isinstance(records, list) or not (
        1 <= len(records) <= MAX_EVIDENCE_ARTICLES
    ):
        raise MetadataError("invalid evidence schema version or article count")
    if review_near_duplicates and len(records) > MAX_NEAR_ARTICLES:
        raise MetadataError("near-duplicate review exceeds article count budget")
    root = manifest_path.parent.resolve()
    by_source: dict[str, str] = {}
    by_hash: dict[str, str] = {}
    text_fingerprints: dict[str, str] = {}
    reviewed_bytes = 0
    near_chars = 0
    shingles_by_source: dict[str, set[str]] = {}
    excluded_sources: list[str] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict) or set(item) != {"source", "file", "sha256"}:
            raise MetadataError(f"evidence article {index}: expected source/file/sha256")
        source, rel, expected = item["source"], item["file"], item["sha256"]
        if not isinstance(source, str) or not source or source != source.strip():
            raise MetadataError(f"evidence article {index}: invalid source identifier")
        if not isinstance(rel, str) or (
            not rel or chr(92) in rel or
            any(part in ("", ".", "..") for part in rel.split("/"))
            or Path(rel).is_absolute()
        ):
            raise MetadataError(f"evidence article {index}: unsafe relative file path")
        if not isinstance(expected, str) or not SHA256_PATTERN.fullmatch(expected):
            raise MetadataError(f"evidence article {index}: invalid sha256")
        if source in by_source:
            raise MetadataError(f"duplicate evidence source identifier at article {index}")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise MetadataError(f"evidence article {index}: path escapes manifest directory") from exc
        if not target.is_file():
            raise MetadataError(f"evidence article {index}: missing article text file")
        if target.stat().st_size > MAX_ARTICLE_BYTES:
            raise MetadataError(f"evidence article {index}: text exceeds size limit")
        digest = hashlib.sha256()
        size = 0
        body = bytearray() if review_text else None
        with target.open("rb") as handle:
            for block in iter(lambda: handle.read(65536), b""):
                size += len(block)
                if size > MAX_ARTICLE_BYTES:
                    raise MetadataError(f"evidence article {index}: text exceeds size limit")
                digest.update(block)
                if body is not None:
                    reviewed_bytes += len(block)
                    if reviewed_bytes > 100_000_000:
                        raise MetadataError("text review exceeds total 100 MB byte budget")
                    body.extend(block)
        if size == 0 or digest.hexdigest() != expected:
            raise MetadataError(f"evidence article {index}: empty or sha256 mismatch")
        if expected in by_hash:
            raise MetadataError(f"duplicate article content at article {index}")
        by_source[source] = rel
        by_hash[expected] = source
        if body is not None:
            try:
                normalized = normalize_article_text(body)
                text_fingerprints[source] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                if review_near_duplicates:
                    near_chars += len(normalized)
                    if near_chars > MAX_NEAR_TOTAL_CHARS:
                        raise ValueError("near-duplicate review exceeds total normalized character budget")
                    shingles = character_shingles(normalized)
                    if shingles:
                        shingles_by_source[source] = shingles
                    else:
                        excluded_sources.append(source)
            except ValueError as exc:
                raise MetadataError(f"evidence article {index}: {exc}") from exc
    used = {
        parse_provenance(row.get("Notes", ""), label)[1]["來源"]
        for label, row in candidates.items()
    }
    missing = sorted(used - by_source.keys())
    if missing:
        raise MetadataError(f"candidate sources not found in evidence manifest: {missing}")
    result = {
        "EvidenceArticlesChecked": len(records),
        "CandidateSourcesMatched": len(used),
        "UnusedEvidenceArticles": len(by_source.keys() - used),
        "EvidenceByteHashesVerified": True,
        "SourceAuthenticityVerified": False,
        "EvidenceSemanticRelevanceVerified": False,
        "Approved": False,
        "AuthoritativeFilesModified": False,
    }
    if review_text:
        groups = normalized_duplicate_groups(text_fingerprints)
        result.update({
            "TextReviewStatus": "REVIEW_REQUIRED" if groups else "NO_NORMALIZED_DUPLICATES_FOUND",
            "TextReviewArticlesChecked": len(text_fingerprints),
            "NormalizedDuplicateSourceGroups": groups,
            "TextReviewNormalization": "UTF8_BOM_NFC_UNICODE_WHITESPACE_V1",
            "NearDuplicateSearchPerformed": False,
        })
    if review_near_duplicates:
        pairs = near_duplicate_pairs(text_fingerprints, shingles_by_source)
        status = ("REVIEW_REQUIRED" if pairs else
                  "INCOMPLETE_SHORT_OR_REPETITIVE" if excluded_sources else
                  "NO_CANDIDATE_PAIRS_FOUND")
        result.update({
            "NearDuplicateSearchPerformed": True,
            "NearDuplicateReviewStatus": status,
            "NearDuplicateMethod": "NORMALIZED_CHARACTER_5GRAM_JACCARD_V1",
            "NearDuplicateThreshold": 0.8,
            "NearDuplicateEligibleArticles": len(shingles_by_source),
            "NearDuplicateExcludedSources": sorted(excluded_sources),
            "NearDuplicateCoverageComplete": not excluded_sources,
            "NearDuplicatePairs": pairs,
            "SemanticSimilarityVerified": False,
        })
        if pairs:
            result["TextReviewStatus"] = "REVIEW_REQUIRED"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only validation of AI ClassTable proposals (not approval)"
    )
    parser.add_argument("--base", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--base-tree", type=Path)
    parser.add_argument("--edges", type=Path)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--review-text", action="store_true",
                        help="Review UTF-8 text and report formatting-normalized duplicates (not approval)")
    parser.add_argument("--review-near-duplicates", action="store_true",
                        help="Opt-in bounded lexical similarity review; requires --review-text")
    args = parser.parse_args(argv)
    if (args.base_tree is None) != (args.edges is None):
        parser.error("--base-tree and --edges must be provided together")
    if args.review_near_duplicates and not args.review_text:
        parser.error("--review-near-duplicates requires --review-text")
    if args.review_text and args.evidence_manifest is None:
        parser.error("--review-text requires --evidence-manifest")
    try:
        candidates = load_class_table(args.candidates)
        report = audit_proposals(load_class_table(args.base), candidates)
        if args.evidence_manifest is not None:
            report.update(audit_local_article_evidence(
                candidates, args.evidence_manifest, review_text=args.review_text,
                review_near_duplicates=args.review_near_duplicates,
            ))
        if args.base_tree is not None:
            report.update(audit_proposed_graph_nodes(
                report["AI新增"], base_tree=args.base_tree, proposed_edges=args.edges
            ))
    except (MetadataError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(
            f"Validated {report['CandidateCount']} candidate(s): "
            f"{len(report['AI新增'])} proposed additions, "
            f"{len(report['AI補充'])} proposed supplements; "
            "all PENDING human review; no files modified."
        )
        if args.review_text:
            print(f"Text review: {report['TextReviewStatus']}; "
                  f"{len(report['NormalizedDuplicateSourceGroups'])} normalized duplicate group(s).")
        if args.review_near_duplicates:
            print(f"Near-duplicate review: {report['NearDuplicateReviewStatus']}; "
                  f"{len(report['NearDuplicatePairs'])} pair(s), "
                  f"{len(report['NearDuplicateExcludedSources'])} excluded source(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
