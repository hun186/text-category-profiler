"""Read-only KI-012 stage candidate inventory for an OFFLINE, QUIESCENT COPY.

Never connects to live WorkPool, never changes SQLite schema/data and NEVER
drops candidate tables. A matching name alone CANNOT prove that a candidate
is orphaned or safe to delete. Supply only a copy taken when writing is stopped.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3

from scripts.bl001_stage_sqlite_audit import _readonly_uri, audit_stage_sqlite


_CANDIDATE = re.compile(r"__bl001_stage_[0-9a-f]{32}\Z")
_PREFIX = "__bl001_stage_"
_DISPLAY_LIMIT = 20


def inventory_offline_copy(filename: str | Path) -> dict:
    path = Path(filename)
    result = {
        "status": "UNVERIFIABLE",
        "scope": "offline_quiescent_copy_readonly",
        "database": str(path),
        "candidate_count": 0,
        "candidate_names": [],
        "candidate_names_truncated": False,
        "unexpected_prefix_count": 0,
        "unexpected_prefixed_names": [],
        "unexpected_names_truncated": False,
        "schema_status": "NOT_CHECKED",
        "issues": [],
        "safety": (
            "Names do not identify live or orphan ownership; NEVER auto-delete. "
            "No row data read; this is not a live-DB or cleanup approval."
        ),
    }
    issues = result["issues"]
    # Immutable/read-only does not make a live WorkPool DB a safe source:
    # reject submitted spelling and resolved path (symlinked parent aliases).
    submitted_parts = (part.casefold() for part in path.parent.parts)
    resolved_parts = (part.casefold() for part in path.parent.resolve(strict=False).parts)
    if any(part.startswith("workpool") for part in (*submitted_parts, *resolved_parts)):
        issues.append("workpool_path_not_allowed")
        return result
    if path.is_symlink():
        issues.append("symlink_not_allowed")
        return result
    if not path.is_file():
        issues.append("database_not_found")
        return result
    if any(Path(str(path) + suffix).exists()
           for suffix in ("-wal", "-shm", "-journal")):
        issues.append("sqlite_journal_or_wal_present")
        return result
    try:
        if path.stat().st_size < 100:
            issues.append("database_empty_or_truncated")
            return result
        with closing(sqlite3.connect(_readonly_uri(path), uri=True, timeout=1)) as db:
            db.execute("PRAGMA query_only=ON")
            names = [
                row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
    except (OSError, sqlite3.Error, ValueError):
        issues.append("database_unreadable_or_invalid")
        return result

    candidates = [name for name in names if _CANDIDATE.fullmatch(name)]
    suspicious = [
        name for name in names
        if name.startswith(_PREFIX) and not _CANDIDATE.fullmatch(name)
    ]
    result["candidate_count"] = len(candidates)
    result["candidate_names"] = candidates[:_DISPLAY_LIMIT]
    result["candidate_names_truncated"] = len(candidates) > _DISPLAY_LIMIT
    result["unexpected_prefix_count"] = len(suspicious)
    result["unexpected_prefixed_names"] = suspicious[:_DISPLAY_LIMIT]
    result["unexpected_names_truncated"] = len(suspicious) > _DISPLAY_LIMIT

    # A candidate count cannot certify anything if the main stage schema is
    # corrupted. Reuse the existing fail-closed schema-only audit.
    audit = audit_stage_sqlite(path)
    result["schema_status"] = audit["status"]
    if audit["status"] != "PASS":
        issues.append("main_stage_schema_not_verified")
        issues.extend(audit["issues"])
        return result

    result["status"] = (
        "REVIEW_REQUIRED" if candidates or suspicious else "PASS_NO_CANDIDATES"
    )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="READ-ONLY candidate-table inventory on a quiescent SQLite COPY; never cleans."
    )
    parser.add_argument(
        "--db", required=True, help="A separate OFFLINE SQLite copy; NOT the live WorkPool DB"
    )
    args = parser.parse_args(argv)
    report = inventory_offline_copy(args.db)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return {"PASS_NO_CANDIDATES": 0, "REVIEW_REQUIRED": 1}.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
