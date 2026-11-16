"""Metadata-only inbound-FK/attached-trigger scan on detached SQLite COPY.

Use after stopping all writers and preparing an independent copy outside
WorkPool. Never writes, repairs, deletes or authorizes production replacement.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from scripts.bl001_stage_sqlite_audit import _readonly_uri
from scripts.bl001_stage_sqlite_candidate_inventory import inventory_offline_copy


_DETAIL_LIMIT = 20


def _identity(path: Path) -> tuple[int, int, int, int, int, int]:
    stat = path.stat()
    return (stat.st_dev, stat.st_ino, stat.st_nlink,
            stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def inspect_offline_replacement_dependencies(filename: str | Path) -> dict:
    path = Path(filename)
    report = {
        "status": "UNVERIFIABLE",
        "scope": "detached_offline_sqlite_schema_metadata_only",
        "database": str(path),
        "trigger_count": 0,
        "attached_trigger_names": [],
        "trigger_names_truncated": False,
        "inbound_foreign_key_count": 0,
        "referencing_table_names": [],
        "referencing_names_truncated": False,
        "candidate_count": 0,
        "issues": [],
        "replacement_authorized": False,
        "candidate_owner_status": "UNKNOWN",
        "candidate_deletion_authorized": False,
        "production_workpool_verified": False,
        "limits": (
            "Only schema metadata from a stopped-writer copy; no row data "
            "or live WorkPool is inspected. A clear result is not permission "
            "to replace a database or clean candidate tables."
        ),
    }
    # Enforce the hard-link boundary BEFORE inventory opens SQLite:
    # a detached-looking hard link may still be the live WorkPool inode.
    try:
        if path.is_file() and path.stat().st_nlink != 1:
            report["issues"].append("hardlink_not_allowed")
            return report
    except (OSError, ValueError):
        report["issues"].append("database_path_not_verifiable")
        return report
    source = inventory_offline_copy(path)
    report["candidate_count"] = source["candidate_count"]
    if source["status"] == "UNVERIFIABLE":
        report["issues"] = source["issues"][:]
        return report
    try:
        before = _identity(path)
        if before[2] != 1:
            report["issues"].append("hardlink_not_allowed")
            return report
        with closing(sqlite3.connect(
            _readonly_uri(path), uri=True, timeout=1,
        )) as db:
            db.execute("PRAGMA query_only=ON")
            entries = list(db.execute(
                "SELECT type, name, tbl_name FROM sqlite_master "
                "WHERE type IN ('table', 'trigger') ORDER BY type, name"
            ))
            triggers = sorted(
                name for kind, name, owner in entries
                if kind == "trigger" and owner.casefold() == "samplesrc"
            )
            inbound = []
            for kind, name, _ in entries:
                if kind != "table" or name.casefold() == "samplesrc":
                    continue
                quoted = '"' + name.replace('"', '""') + '"'
                for fk in list(db.execute(
                    "PRAGMA foreign_key_list(" + quoted + ")"
                )):
                    if fk[2].casefold() == "samplesrc":
                        inbound.append(name)
        after = _identity(path)
        ending = inventory_offline_copy(path)
        if (before != after
                or ending["status"] != source["status"]
                or ending["candidate_count"] != source["candidate_count"]
                or ending["unexpected_prefix_count"]
                != source["unexpected_prefix_count"]
                or ending["candidate_names_sha256"]
                != source["candidate_names_sha256"]
                or ending["unexpected_prefix_names_sha256"]
                != source["unexpected_prefix_names_sha256"]):
            report["issues"].append("offline_schema_changed_during_inventory")
            return report
    except (OSError, ValueError, sqlite3.Error):
        report["issues"].append("dependency_metadata_unreadable")
        return report
    report["trigger_count"] = len(triggers)
    report["attached_trigger_names"] = triggers[:_DETAIL_LIMIT]
    report["trigger_names_truncated"] = len(triggers) > _DETAIL_LIMIT
    table_names = sorted(set(inbound))
    report["inbound_foreign_key_count"] = len(inbound)
    report["referencing_table_names"] = table_names[:_DETAIL_LIMIT]
    report["referencing_names_truncated"] = len(table_names) > _DETAIL_LIMIT
    report["status"] = (
        "REVIEW_REQUIRED" if triggers or inbound
        or source["status"] == "REVIEW_REQUIRED"
        else "NO_DEPENDENCIES_OBSERVED"
    )
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only schema dependency scan on detached SQLite COPY.")
    parser.add_argument("--db", required=True,
                        help="Independent stopped-writer copy, never WorkPool")
    args = parser.parse_args(argv)
    report = inspect_offline_replacement_dependencies(args.db)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return {"NO_DEPENDENCIES_OBSERVED": 0, "REVIEW_REQUIRED": 1}.get(
        report["status"], 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
