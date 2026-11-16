"""Private-only KI-012 SQLite backup/restore equivalence diagnostic.

Creates all three DBs in one TemporaryDirectory. Deliberately preserves
unknown candidate table metadata/rows: backing up must never authorize DROP.
No live or external WorkPool input is accepted.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from text_category_profiler.data.stage_sql import write_stage_sql


def _snapshot(path: Path) -> dict:
    """Inspect only known data created by this PRIVATE test."""
    with closing(sqlite3.connect(path)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        names = tuple(db.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
        ).fetchall())
        source_rows = tuple(db.execute(
            'SELECT "index", "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall())
        view_rows = tuple(db.execute(
            'SELECT "text" FROM "source_view" ORDER BY "text"'
        ).fetchall())
        sentinel = tuple(db.execute(
            'SELECT "note" FROM "unrelated"'
        ).fetchall())
        candidate = "__bl001_stage_" + "a" * 32
        candidate_rows = tuple(db.execute(
            'SELECT "text" FROM "' + candidate + '"'
        ).fetchall())
        indexes = {}
        for index_name in ("text_Index", "ix_sampleSrc_index"):
            info = db.execute('PRAGMA index_list("sampleSrc")').fetchall()
            record = [row for row in info if row[1] == index_name]
            keys = tuple(
                (row[2], row[3], row[4]) for row in db.execute(
                    'PRAGMA index_xinfo("' + index_name + '")'
                ) if row[5] == 1
            )
            indexes[index_name] = (tuple(record), keys)
        return {
            "integrity": integrity,
            "schema": names,
            "rows": source_rows,
            "view": view_rows,
            "sentinel": sentinel,
            "candidate": candidate_rows,
            "indexes": indexes,
        }


def check_private_backup_restore(*, rows: int = 40) -> dict:
    if not 5 <= rows <= 500:
        raise ValueError("rows must be between 5 and 500")
    import pandas as pd

    with tempfile.TemporaryDirectory(prefix="ki012-private-backup-restore-") as tmp:
        root = Path(tmp)
        source = root / "source.sqlite3"
        backup = root / "backup.sqlite3"
        restored = root / "restored.sqlite3"
        frame = pd.DataFrame({
            "text": [f"繁體中文_{i}" for i in range(rows)],
            "label": [f"label_{i % 5}" for i in range(rows)],
        })
        write_stage_sql(str(source), frame, [], sqlite3.connect)
        candidate = "__bl001_stage_" + "a" * 32
        with closing(sqlite3.connect(source)) as db:
            db.execute('CREATE TABLE "unrelated" ("note" TEXT)')
            db.execute('INSERT INTO "unrelated" VALUES (?)', ("不得遺失",))
            db.execute('CREATE VIEW "source_view" AS SELECT text FROM sampleSrc')
            db.execute('CREATE TABLE "' + candidate + '" ("text" TEXT)')
            db.execute('INSERT INTO "' + candidate + '" VALUES (?)', ("所有權未知",))
            db.commit()
        before_bytes = source.read_bytes()
        expected = _snapshot(source)
        if expected["integrity"] != "ok":
            raise AssertionError("Initial private source integrity failed")
        with closing(sqlite3.connect(source)) as src:
            with closing(sqlite3.connect(backup)) as dest:
                src.backup(dest)
        saved = _snapshot(backup)
        with closing(sqlite3.connect(backup)) as src:
            with closing(sqlite3.connect(restored)) as dest:
                src.backup(dest)
        actual = _snapshot(restored)
        if before_bytes != source.read_bytes():
            raise AssertionError("Private original was modified by backup")
        if expected != saved or expected != actual:
            raise AssertionError("SQLite backup/restore changed source schema or rows")
        if len(actual["rows"]) != rows:
            raise AssertionError("Restored private sampleSrc count incorrect")
        if actual["candidate"] != (("所有權未知",),):
            raise AssertionError("Unknown candidate was silently discarded")
        if actual["indexes"]["text_Index"][1] != (
                ("text", 0, "BINARY"),):
            raise AssertionError("Wrong restored text index")
        if actual["indexes"]["ix_sampleSrc_index"][1] != (
                ("index", 0, "BINARY"),):
            raise AssertionError("Wrong restored pandas index")
        return {
            "status": "PASS_PRIVATE_BACKUP_RESTORE",
            "scope": "private_tempfile_only_no_workpool",
            "rows": rows,
            "source_preserved": True,
            "backup_matches_source": True,
            "restored_matches_source": True,
            "dependent_view_preserved": True,
            "indexes_verified": True,
            "unknown_candidate_preserved": True,
            "candidate_owner_status": "UNKNOWN",
            "candidate_deletion_authorized": False,
            "production_workpool_verified": False,
            "limits": (
                "sqlite3.backup on three newly-created private SQLite files. "
                "No live WorkPool backup, power failure, external filesystems, "
                "OS disk exhaustion or production recovery is tested."
            ),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="PRIVATE SQLite backup/recovery check. No external DB path.")
    parser.add_argument("--rows", type=int, default=40)
    args = parser.parse_args(argv)
    try:
        result = check_private_backup_restore(rows=args.rows)
    except Exception as exc:
        result = {
            "status": "FAIL_OR_BLOCKED", "error_type": type(exc).__name__,
            "reason": str(exc), "production_workpool_verified": False,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS_PRIVATE_BACKUP_RESTORE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
