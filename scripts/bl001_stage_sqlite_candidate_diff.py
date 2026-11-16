"""Metadata-only comparison of TWO quiescent offline SQLite copies.

Neither source may be a WorkPool-path database or an active DB. SQLite
candidate names cannot prove ownership. This tool has zero delete/cleanup
paths and does not read user data rows.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from scripts.bl001_stage_sqlite_audit import _readonly_uri
from scripts.bl001_stage_sqlite_candidate_inventory import (
    _CANDIDATE, _DISPLAY_LIMIT, _PREFIX, _name_digest, inventory_offline_copy,
)


def _read_candidate_names(path: Path) -> tuple[set[str], set[str]]:
    with closing(sqlite3.connect(_readonly_uri(path), uri=True, timeout=1)) as db:
        db.execute("PRAGMA query_only=ON")
        names = [
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
    candidates = {name for name in names if _CANDIDATE.fullmatch(name)}
    malformed = {
        name for name in names
        if name.startswith(_PREFIX) and not _CANDIDATE.fullmatch(name)
    }
    return candidates, malformed


def _file_identity(path: Path) -> tuple[int, int, int, int, int]:
    """Metadata sentinel, not proof of quiescence or cryptographic identity."""
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_size,
            stat.st_mtime_ns, stat.st_ctime_ns)


def compare_offline_copies(before: str | Path, after: str | Path) -> dict:
    first, second = Path(before), Path(after)
    report = {
        "status": "UNVERIFIABLE",
        "scope": "two_offline_quiescent_copies_readonly",
        "before": str(first), "after": str(second),
        "before_status": "NOT_CHECKED", "after_status": "NOT_CHECKED",
        "issues": [],
        "owner_status": "UNKNOWN", "deletion_authorized": False,
        "production_workpool_verified": False,
        "note": (
            "Candidate name changes cannot identify table ownership or "
            "authorize cleanup. Only schema metadata is read."
        ),
    }
    # Do not open any DB when both arguments point to one physical file.
    try:
        if first.resolve(strict=False) == second.resolve(strict=False):
            report["issues"].append("distinct_offline_copies_required")
            return report
        if first.is_file() and second.is_file() and first.samefile(second):
            report["issues"].append("distinct_offline_copies_required")
            return report
    except (OSError, ValueError, RuntimeError):
        report["issues"].append("copy_identity_not_verifiable")
        return report

    pre = inventory_offline_copy(first)
    post = inventory_offline_copy(second)
    report["before_status"] = pre["status"]
    report["after_status"] = post["status"]
    if pre["status"] == "UNVERIFIABLE" or post["status"] == "UNVERIFIABLE":
        report["issues"] = [
            "before:" + msg for msg in pre["issues"]
        ] + ["after:" + msg for msg in post["issues"]]
        return report

    try:
        # If input is unexpectedly changed between validation and the second
        # schema scan, refuse to claim a consistent offline comparison.
        before_identity = _file_identity(first)
        after_identity = _file_identity(second)
        before_candidates, before_malformed = _read_candidate_names(first)
        after_candidates, after_malformed = _read_candidate_names(second)
        if (before_identity != _file_identity(first)
                or after_identity != _file_identity(second)):
            report["issues"].append("offline_copy_changed_during_diff")
            return report
    except (OSError, sqlite3.Error, ValueError):
        report["issues"].append("candidate_comparison_failed")
        return report

    # Verify inventory and comparison scans agreed; detect some non-quiescent
    # changes, but never pretend these checks prove source quiescence.
    if (len(before_candidates) != pre["candidate_count"]
            or len(after_candidates) != post["candidate_count"]
            or len(before_malformed) != pre["unexpected_prefix_count"]
            or len(after_malformed) != post["unexpected_prefix_count"]
            or _name_digest(before_candidates) != pre["candidate_names_sha256"]
            or _name_digest(after_candidates) != post["candidate_names_sha256"]
            or _name_digest(before_malformed) != pre["unexpected_prefix_names_sha256"]
            or _name_digest(after_malformed) != post["unexpected_prefix_names_sha256"]):
        report["issues"].append("snapshot_changed_or_inconsistent")
        return report

    additions = sorted(after_candidates - before_candidates)
    removals = sorted(before_candidates - after_candidates)
    unchanged = len(before_candidates & after_candidates)
    malformed_added = sorted(after_malformed - before_malformed)
    malformed_removed = sorted(before_malformed - after_malformed)
    report.update({
        "before_candidate_count": len(before_candidates),
        "after_candidate_count": len(after_candidates),
        "unchanged_candidate_count": unchanged,
        "added_candidate_count": len(additions),
        "removed_candidate_count": len(removals),
        "added_candidate_names": additions[:_DISPLAY_LIMIT],
        "added_names_truncated": len(additions) > _DISPLAY_LIMIT,
        "removed_candidate_names": removals[:_DISPLAY_LIMIT],
        "removed_names_truncated": len(removals) > _DISPLAY_LIMIT,
        "added_malformed_prefix_count": len(malformed_added),
        "removed_malformed_prefix_count": len(malformed_removed),
        "added_malformed_prefix_names": malformed_added[:_DISPLAY_LIMIT],
        "removed_malformed_prefix_names": malformed_removed[:_DISPLAY_LIMIT],
        "malformed_added_truncated": len(malformed_added) > _DISPLAY_LIMIT,
        "malformed_removed_truncated": len(malformed_removed) > _DISPLAY_LIMIT,
        "status": (
            "REVIEW_REQUIRED" if (before_candidates or after_candidates
                                  or before_malformed or after_malformed)
            else "PASS_NO_CANDIDATES"
        ),
    })
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only metadata diff between TWO quiescent OFFLINE DB copies."
    )
    parser.add_argument("--before", required=True,
                        help="Independent stopped-writer COPY, not live WorkPool")
    parser.add_argument("--after", required=True,
                        help="Independent later COPY, not live WorkPool")
    args = parser.parse_args(argv)
    try:
        result = compare_offline_copies(args.before, args.after)
    except (OSError, ValueError) as err:
        result = {"status": "UNVERIFIABLE", "issues": [type(err).__name__],
                  "owner_status": "UNKNOWN", "deletion_authorized": False,
                  "production_workpool_verified": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {"PASS_NO_CANDIDATES": 0, "REVIEW_REQUIRED": 1}.get(
        result["status"], 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
