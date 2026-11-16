"""Metadata-only KI-012 candidate-table triage on a QUIESCENT SQLite COPY.

No input row reads and no database modification. A candidate's columns/indexes
cannot establish that the original writer is dead, so this CLI NEVER labels
tables safe to delete. Import the existing offline inventory to enforce its
fail-closed source checks, including WorkPool ancestor refusal.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from scripts.bl001_stage_sqlite_audit import _readonly_uri
from scripts.bl001_stage_sqlite_candidate_inventory import inventory_offline_copy


def triage_offline_copy(filename: str | Path) -> dict:
    prior = inventory_offline_copy(filename)
    report = {
        "status": "UNVERIFIABLE",
        "scope": "offline_quiescent_copy_readonly",
        "database": str(filename),
        "candidate_count": prior["candidate_count"],
        "candidates": [],
        "candidate_detail_truncated": prior["candidate_names_truncated"],
        "unexpected_prefix_count_known": len(prior["unexpected_prefixed_names"]),
        "unexpected_prefix_names_truncated": prior["unexpected_names_truncated"],
        "issues": prior["issues"][:],
        "owner_status": "UNKNOWN",
        "deletion_authorized": False,
        "note": (
            "Structural metadata only; a matching candidate may still be active. "
            "No DROP, DELETE, VACUUM or cleanup decision is provided."
        ),
    }
    if prior["status"] == "UNVERIFIABLE":
        return report
    if prior["status"] == "PASS_NO_CANDIDATES":
        report["status"] = "PASS_NO_CANDIDATES"
        return report

    path = Path(filename)
    try:
        with closing(sqlite3.connect(
            _readonly_uri(path), uri=True, timeout=1,
        )) as db:
            db.execute("PRAGMA query_only=ON")
            for candidate in prior["candidate_names"]:
                # Names already match a strict 32-hex allowlist in the
                # inventory; quote them anyway to avoid SQL injection.
                name = '"' + candidate.replace('"', '""') + '"'
                fields = [
                    row[1] for row in db.execute(
                        "PRAGMA table_info(" + name + ")"
                    )
                ]
                indexes = [
                    row[1] for row in db.execute(
                        "PRAGMA index_list(" + name + ")"
                    )
                ]
                expected = "ix_" + candidate + "_index"
                report["candidates"].append({
                    "table": candidate,
                    "column_count": len(fields),
                    "has_text_column": "text" in fields,
                    "has_pandas_index": expected in indexes,
                    "all_index_count": len(indexes),
                    "owner_status": "UNKNOWN",
                    "safe_to_delete": False,
                })
    except (OSError, sqlite3.Error, ValueError):
        report["issues"].append("candidate_metadata_read_failed")
        return report

    report["status"] = "REVIEW_REQUIRED"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Schema-only candidate triage of a QUIESCENT OFFLINE COPY."
    )
    parser.add_argument("--db", required=True,
                        help="Separate stopped-writer copy, never live WorkPool")
    args = parser.parse_args(argv)
    outcome = triage_offline_copy(args.db)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return {"PASS_NO_CANDIDATES": 0, "REVIEW_REQUIRED": 1}.get(
        outcome["status"], 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
