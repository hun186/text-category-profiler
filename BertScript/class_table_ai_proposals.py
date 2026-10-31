"""Read-only provenance gate for AI-generated ClassTable candidate CSVs.

This module never writes the authoritative ClassTable or TopicTree. Passing
validation only means proposal metadata is well-formed, NOT that any taxonomy
change has been approved or that source evidence has been independently checked.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

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


def audit_proposed_graph_nodes(
    additions: list[str],
    *,
    base_tree: str | Path,
    proposed_edges: str | Path,
) -> dict[str, object]:
    """Match proposed new graph node identities to AI新增 labels only.

    Graph relationship semantics, article evidence, cyclicity and actual
    authorization are NOT checked here. This never reads/writes official
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
    return {
        "GraphNodeAlignment": "matched",
        "NewGraphNodes": sorted(added),
        "GraphRelationshipsApproved": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only validation of AI ClassTable proposals (not approval)"
    )
    parser.add_argument("--base", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--base-tree", type=Path)
    parser.add_argument("--edges", type=Path)
    args = parser.parse_args(argv)
    if (args.base_tree is None) != (args.edges is None):
        parser.error("--base-tree and --edges must be provided together")
    try:
        report = audit_proposals(
            load_class_table(args.base), load_class_table(args.candidates)
        )
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
