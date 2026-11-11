"""Read-only schema audit for the BL-001 stage-local sampleSrc SQLite output.

This does not repair, migrate, checkpoint, or read application rows. Use a
quiescent COPY of a stage SQLite database: immutable SQLite deliberately ignores
WAL/rollback state and cannot certify a database being written concurrently.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote


def _readonly_uri(path: Path) -> str:
    """Use an authority-free URI, including Windows UNC network paths."""
    encoded = quote(path.resolve(strict=True).as_posix(), safe="/:")
    if encoded.startswith("//"):
        encoded = "//" + encoded
    return "file:" + encoded + "?mode=ro&immutable=1"


def audit_stage_sqlite(filename: str | Path) -> dict:
    """Check only SQLite schema metadata; never open a writable connection.

    A PASS means a quiescent copy has the expected stage-local schema. It does
    not prove transaction durability, provenance, row correctness, or WorkPool
    acceptance. Fail closed for missing DB, symlinks, and journal sidecars.
    """
    path = Path(filename)
    result = {
        "status": "FAIL",
        "database": str(path),
        "table": "sampleSrc",
        "index": "text_Index",
        "columns": [],
        "index_key_columns": [],
        "index_properties": None,
        "issues": [],
    }
    issues = result["issues"]
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
            table = db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                ("sampleSrc",),
            ).fetchone()
            if table is None:
                issues.append("missing_sampleSrc_table")
            else:
                result["columns"] = [
                    item[1] for item in db.execute(
                        'PRAGMA table_info("sampleSrc")'
                    ).fetchall()
                ]
                if "text" not in result["columns"]:
                    issues.append("missing_text_column")

            index = db.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type='index' AND name=?",
                ("text_Index",),
            ).fetchone()
            if index is None:
                issues.append("missing_text_Index")
            elif index[0] != "sampleSrc":
                issues.append("text_Index_on_wrong_table")
            else:
                # PRAGMA index_xinfo exposes expression keys as cid=-2, even
                # when a legacy double-quoted identifier silently succeeded.
                key_parts = [
                    entry for entry in db.execute(
                        'PRAGMA index_xinfo("text_Index")'
                    ).fetchall() if entry[5] == 1
                ]
                result["index_key_columns"] = [entry[2] for entry in key_parts]
                if (len(key_parts) != 1 or key_parts[0][1] < 0
                        or key_parts[0][2] != "text"):
                    issues.append("text_Index_not_bound_to_text_column")
                elif key_parts[0][3] != 0 or key_parts[0][4] != "BINARY":
                    # A DESC/NOCASE key is not the plain index created by
                    # the Stage-local writer. The audit must not certify it.
                    issues.append("text_Index_wrong_order_or_collation")

                # index_xinfo alone cannot distinguish an ordinary index
                # from UNIQUE or partial indexes with identical key columns.
                # UNIQUE may reject valid duplicate texts; a partial index
                # does not cover every row. Both differ from Stage-local DDL.
                entries = [
                    entry for entry in db.execute(
                        'PRAGMA index_list("sampleSrc")'
                    ).fetchall() if entry[1] == "text_Index"
                ]
                if len(entries) != 1:
                    issues.append("text_Index_not_listed_on_sampleSrc")
                else:
                    entry = entries[0]
                    result["index_properties"] = {
                        "unique": bool(entry[2]),
                        "origin": entry[3],
                        "partial": bool(entry[4]),
                    }
                    if entry[2] != 0 or entry[3] != "c" or entry[4] != 0:
                        issues.append("text_Index_not_plain_nonunique_full")
    except (OSError, sqlite3.Error, ValueError):
        issues.append("database_unreadable_or_invalid")
    if not issues:
        result["status"] = "PASS"
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only BL-001 sampleSrc/text_Index schema audit; use a quiescent copy."
    )
    parser.add_argument("--db", required=True, help="Path to an existing, quiescent SQLite copy")
    args = parser.parse_args(argv)
    outcome = audit_stage_sqlite(args.db)
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0 if outcome["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
