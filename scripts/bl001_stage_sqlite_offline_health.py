"""Bounded integrity quick_check on a QUIESCENT DETACHED SQLite COPY only.

Unlike schema metadata audit, PRAGMA quick_check reads SQLite pages. It never
returns data rows or attempts any repairs. Reject WorkPool-path DBs and
sidecars via the inventory. Do not use against live or network-mounted DB.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from scripts.bl001_stage_sqlite_audit import _readonly_uri
from scripts.bl001_stage_sqlite_candidate_inventory import inventory_offline_copy


def offline_quick_check(filename: str | Path, *, max_mib: int = 256) -> dict:
    if not 1 <= max_mib <= 4096:
        raise ValueError("max_mib must be 1..4096")
    path = Path(filename)
    report = {
        "status": "UNVERIFIABLE",
        "scope": "offline_quiescent_copy_readonly",
        "database": str(path),
        "max_mib": max_mib,
        "candidate_owner_status": "UNKNOWN",
        "candidate_deletion_authorized": False,
        "production_workpool_verified": False,
        "issues": [],
        "quick_check": "NOT_RUN",
        "limitations": (
            "PRAGMA quick_check(1) checks SQLite consistency on a detached "
            "copy only; it does not verify all foreign keys, application "
            "semantics, complete disk durability, or live WorkPool state."
        ),
    }
    # This guard refuses live-looking WorkPool ancestry, symlinks, sidecars,
    # unreadable files and failed sampleSrc/text_Index schema before opening.
    source = inventory_offline_copy(path)
    report["candidate_count"] = source["candidate_count"]
    report["unexpected_prefix_count"] = source["unexpected_prefix_count"]
    if source["status"] == "UNVERIFIABLE":
        report["issues"] = source["issues"][:]
        return report
    try:
        first = path.stat()
        limit = max_mib * 1024 * 1024
        if first.st_size > limit:
            report["issues"].append("offline_copy_exceeds_bounded_scan_limit")
            return report
        # A user-chosen existing, quiescent detached COPY is opened immutable:
        # no WAL checkpoint, journal writes, or locks that can alter it.
        with closing(sqlite3.connect(_readonly_uri(path), uri=True, timeout=1)) as db:
            db.execute("PRAGMA query_only=ON")
            rows = db.execute("PRAGMA quick_check(1)").fetchall()
        last = path.stat()
        if (first.st_size != last.st_size
                or first.st_mtime_ns != last.st_mtime_ns
                or getattr(first, "st_ino", None) != getattr(last, "st_ino", None)):
            report["issues"].append("offline_copy_changed_during_check")
            return report
        if len(rows) != 1 or rows[0][0] != "ok":
            report["issues"].append("sqlite_quick_check_not_ok")
            report["quick_check"] = "FAIL"
            return report
        report["quick_check"] = "ok"
        report["checked_db_bytes"] = first.st_size
        report["status"] = (
            "REVIEW_REQUIRED" if source["status"] == "REVIEW_REQUIRED"
            else "PASS_OFFLINE_QUICK_CHECK"
        )
        return report
    except (OSError, sqlite3.Error, ValueError):
        report["issues"].append("sqlite_quick_check_unverifiable")
        return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded read-only SQLite quick_check on an offline COPY."
    )
    parser.add_argument("--db", required=True,
                        help="Stopped-writer independent detached SQLite copy")
    parser.add_argument("--max-mib", type=int, default=256)
    args = parser.parse_args(argv)
    try:
        result = offline_quick_check(args.db, max_mib=args.max_mib)
    except ValueError as err:
        result = {
            "status": "UNVERIFIABLE", "issues": [str(err)],
            "candidate_owner_status": "UNKNOWN",
            "candidate_deletion_authorized": False,
            "production_workpool_verified": False,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return {"PASS_OFFLINE_QUICK_CHECK": 0, "REVIEW_REQUIRED": 1}.get(
        result["status"], 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
