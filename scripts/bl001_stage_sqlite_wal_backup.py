"""Private SQLite WAL-mode backup/restore contract, never live WorkPool.

A WAL-mode source has uncheckpointed committed changes and a sidecar while a
writer is held open. SQLite backup API must include those committed changes.
Only a bounded TemporaryDirectory is used; no database path is accepted.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from scripts.bl001_stage_sqlite_candidate_inventory import inventory_offline_copy
from text_category_profiler.data.stage_sql import write_stage_sql


_CANDIDATE = "__bl001_stage_" + "c" * 32


def _verify_detached(path: Path, rows: int) -> None:
    with closing(sqlite3.connect(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("Backup SQLite integrity failed")
        actual = db.execute(
            'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()
        expected = [(f"WAL-中文-{i}", "new") for i in range(rows)]
        if actual != expected:
            raise AssertionError("Committed WAL rows missing from backup")
        view = sorted(db.execute('SELECT "text" FROM "source_view"').fetchall())
        if view != sorted((row[0],) for row in expected):
            raise AssertionError("Dependent view rows differ")
        if db.execute('SELECT "note" FROM "unrelated"').fetchall() != [
                ("保留",)]:
            raise AssertionError("Unrelated table missing")
        quoted = '"' + _CANDIDATE + '"'
        if db.execute('SELECT "text" FROM ' + quoted).fetchall() != [
                ("owner-unknown",)]:
            raise AssertionError("Unknown candidate not preserved")
        indexes = {
            row[1]: row for row in db.execute('PRAGMA index_list("sampleSrc")')
        }
        if set(indexes) != {"text_Index", "ix_sampleSrc_index"}:
            raise AssertionError("Missing restored Stage indexes")
        for name, key in (("text_Index", "text"),
                          ("ix_sampleSrc_index", "index")):
            record = indexes[name]
            if record[2:5] != (0, "c", 0):
                raise AssertionError("Index uniqueness/partial contract changed")
            parts = [
                row for row in db.execute(
                    'PRAGMA index_xinfo("' + name + '")'
                ) if row[5] == 1
            ]
            if (len(parts) != 1 or parts[0][1] < 0
                    or parts[0][2] != key
                    or parts[0][3] != 0 or parts[0][4] != "BINARY"):
                raise AssertionError("Index target column is incorrect")


def _copy_by_sqlite_backup(source: Path, target: Path) -> None:
    with closing(sqlite3.connect(source)) as from_db:
        with closing(sqlite3.connect(target)) as to_db:
            from_db.backup(to_db)
    # Backups are newly created private temp files. Normalize *only these*
    # destinations to a self-contained rollback-journal SQLite file.
    with closing(sqlite3.connect(target)) as detached:
        mode = detached.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
        if mode.lower() != "delete":
            raise AssertionError("Private backup destination not detached")
        detached.commit()


def private_wal_backup(*, rows: int = 40) -> dict:
    if not 10 <= rows <= 500:
        raise ValueError("rows must be 10..500")
    import pandas as pd

    with tempfile.TemporaryDirectory(prefix="ki012-wal-backup-private-") as tmp:
        root = Path(tmp)
        source, backup, restored = (root / "source.sqlite3",
                                    root / "backup.sqlite3",
                                    root / "restored.sqlite3")
        frame = pd.DataFrame({
            "text": [f"WAL-中文-{i}" for i in range(rows)],
            "label": ["new"] * rows,
        })
        write_stage_sql(str(source), frame, [], sqlite3.connect)
        with closing(sqlite3.connect(source)) as writer:
            mode = writer.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if mode.lower() != "wal":
                raise AssertionError("Unable to enable private WAL source")
            writer.execute('CREATE VIEW "source_view" AS SELECT "text" FROM "sampleSrc"')
            writer.execute('CREATE TABLE "unrelated" ("note" TEXT)')
            writer.execute('INSERT INTO "unrelated" VALUES (?)', ("保留",))
            writer.execute('CREATE TABLE "' + _CANDIDATE + '" ("text" TEXT)')
            writer.execute(
                'INSERT INTO "' + _CANDIDATE + '" VALUES (?)',
                ("owner-unknown",),
            )
            writer.commit()
            wal_path = Path(str(source) + "-wal")
            if not wal_path.is_file() or wal_path.stat().st_size == 0:
                raise AssertionError("Private WAL sidecar not present after commit")
            # Existing offline inventory must never certify the live-WAL input
            # as a clean, quiescent SQLite file.
            source_report = inventory_offline_copy(source)
            if (source_report["status"] != "UNVERIFIABLE"
                    or "sqlite_journal_or_wal_present" not in source_report["issues"]):
                raise AssertionError("WAL source was not refused by offline inventory")

            _copy_by_sqlite_backup(source, backup)
            backup_report = inventory_offline_copy(backup)
            if (backup_report["status"] != "REVIEW_REQUIRED"
                    or backup_report["candidate_count"] != 1):
                raise AssertionError("Private backup incorrectly cleared candidate")
            _verify_detached(backup, rows)
            _copy_by_sqlite_backup(backup, restored)
            restored_report = inventory_offline_copy(restored)
            if (restored_report["status"] != "REVIEW_REQUIRED"
                    or restored_report["candidate_count"] != 1):
                raise AssertionError("Private restored copy lost candidate")
            _verify_detached(restored, rows)
            return {
                "status": "PASS_PRIVATE_WAL_BACKUP",
                "scope": "private_tempfile_only_no_workpool",
                "rows": rows,
                "source_wal_detected_and_refused_for_offline_inventory": True,
                "committed_wal_rows_in_backup": True,
                "backup_restored_with_indexes_and_view": True,
                "unknown_candidate_preserved": True,
                "candidate_owner_status": "UNKNOWN",
                "candidate_deletion_authorized": False,
                "production_workpool_verified": False,
                "limits": (
                    "Only locally created private WAL source and SQLite backup "
                    "destinations. Not active production WorkPool backup, crash "
                    "recovery, power loss, network filesystem or disk exhaustion."
                ),
            }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded PRIVATE SQLite WAL backup acceptance; no DB path.")
    parser.add_argument("--rows", type=int, default=40)
    args = parser.parse_args(argv)
    try:
        report = private_wal_backup(rows=args.rows)
    except Exception as err:
        report = {"status": "FAIL_OR_BLOCKED",
                  "error_type": type(err).__name__, "reason": str(err),
                  "production_workpool_verified": False}
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "PASS_PRIVATE_WAL_BACKUP" else 1


if __name__ == "__main__":
    raise SystemExit(main())
