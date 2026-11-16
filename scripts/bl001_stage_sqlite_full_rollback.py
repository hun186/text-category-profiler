"""KI-012: real SQLite SQLITE_FULL injection on a disposable private DB.

Sets PRAGMA max_page_count at the candidate-to-final swap boundary.
This is a database page-quota failure, NOT proof of operating-system disk
exhaustion or the production WorkPool's recovery behavior.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from text_category_profiler.data.stage_sql import write_stage_sql


def run_private_sqlite_full(*, rows: int = 500, repeat: int = 200) -> dict:
    if not 100 <= rows <= 2000 or not 64 <= repeat <= 512:
        raise ValueError("Bounds: rows 100..2000, repeat 64..512")
    import pandas as pd

    with tempfile.TemporaryDirectory(prefix="ki012-private-sqlite-full-") as tmp:
        db_path = Path(tmp) / "quota.sqlite3"
        baseline = pd.DataFrame({"text": ["原始重要資料"], "label": ["old"]})
        write_stage_sql(str(db_path), baseline, [], sqlite3.connect)
        with closing(sqlite3.connect(db_path)) as db:
            db.execute('CREATE TABLE "unrelated" (note TEXT)')
            db.execute('INSERT INTO "unrelated" VALUES (?)', ("應保留",))
            db.execute('CREATE VIEW "source_view" AS SELECT text FROM sampleSrc')
            db.commit()
            before = {
                "rows": db.execute('SELECT text, label FROM sampleSrc').fetchall(),
                "indexes": {r[1] for r in db.execute('PRAGMA index_list("sampleSrc")')},
                "view": db.execute('SELECT text FROM source_view').fetchall(),
                "unrelated": db.execute('SELECT note FROM unrelated').fetchall(),
            }

        quota = {"installed": False, "page_count": None, "max_page_count": None}

        class LimitedConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql.startswith("BEGIN IMMEDIATE"):
                    count = super().execute("PRAGMA page_count").fetchone()[0]
                    limit = super().execute(
                        "PRAGMA max_page_count=" + str(count)
                    ).fetchone()[0]
                    quota.update(installed=True, page_count=count,
                                 max_page_count=limit)
                    if limit != count:
                        raise AssertionError("SQLite page quota did not lock")
                return super().execute(sql, *args, **kwargs)

        replacement = pd.DataFrame({
            "text": [("新資料" + str(i) + "中文") * repeat for i in range(rows)],
            "label": ["new"] * rows,
        })
        error_name = None
        try:
            write_stage_sql(
                str(db_path), replacement, [],
                lambda filename: sqlite3.connect(
                    filename, factory=LimitedConnection,
                ),
            )
        except sqlite3.OperationalError as error:
            error_name = getattr(error, "sqlite_errorname", None)
            if (getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_FULL
                    and "database or disk is full" not in str(error).lower()):
                raise
        if not quota["installed"] or error_name is None:
            raise AssertionError("Expected genuine SQLite full-database error")

        with closing(sqlite3.connect(db_path)) as db:
            after = {
                "rows": db.execute('SELECT text, label FROM sampleSrc').fetchall(),
                "indexes": {r[1] for r in db.execute('PRAGMA index_list("sampleSrc")')},
                "view": db.execute('SELECT text FROM source_view').fetchall(),
                "unrelated": db.execute('SELECT note FROM unrelated').fetchall(),
            }
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            text_keys = [r[2] for r in db.execute('PRAGMA index_xinfo("text_Index")')
                         if r[5] == 1]
            leftover = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) if r[0].startswith("__bl001_stage_")]
        if (before != after or integrity != "ok" or text_keys != ["text"]
                or leftover):
            raise AssertionError("SQLite full error failed safe rollback contract")

        # Prove recovery separately: after SQLITE_FULL rolls back, relax only
        # this TEMP database's page quota and retry through the actual writer.
        with closing(sqlite3.connect(db_path)) as db:
            reset_limit = db.execute(
                "PRAGMA max_page_count=100000"
            ).fetchone()[0]
            db.commit()
            if reset_limit != 100000:
                raise AssertionError("Could not restore private database quota")
        write_stage_sql(str(db_path), replacement, [], sqlite3.connect)
        with closing(sqlite3.connect(db_path)) as db:
            retry_count = db.execute(
                'SELECT COUNT(*) FROM "sampleSrc"'
            ).fetchone()[0]
            new_count = db.execute(
                'SELECT COUNT(*) FROM "sampleSrc" WHERE "label"=?',
                ("new",),
            ).fetchone()[0]
            # source_view exposes only text, not the pandas "index" field.
            # Compare as multisets without relying on SQLite rowid scan order.
            expected_view = sorted((value,) for value in replacement["text"])
            actual_view = sorted(db.execute(
                'SELECT "text" FROM "source_view"'
            ).fetchall())
            retry_keys = [
                key[2] for key in db.execute('PRAGMA index_xinfo("text_Index")')
                if key[5] == 1
            ]
            retry_index_names = {
                item[1] for item in db.execute('PRAGMA index_list("sampleSrc")')
            }
            related = db.execute(
                'SELECT note FROM "unrelated"'
            ).fetchall()
            retry_integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            retry_candidates = [
                row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ) if row[0].startswith("__bl001_stage_")
            ]
        if (retry_count != rows or new_count != rows
                or actual_view != expected_view or retry_keys != ["text"] or retry_index_names != before["indexes"]
                or related != [("應保留",)] or retry_integrity != "ok"
                or retry_candidates):
            raise AssertionError("Private quota-release retry or view contract failed")

        return {
            "status": "PASS_SQLITE_FULL_ROLLBACK",
            "scope": "private_tempfile_only_no_workpool",
            "rows": rows, "text_repeat": repeat,
            "sqlite_error_name": error_name,
            "quota_at_swap": quota,
            "original_rows_preserved": True,
            "text_index_preserved": True,
            "dependent_view_preserved": True,
            "unrelated_table_preserved": True,
            "candidate_tables_remaining": 0,
            "integrity_check": integrity,
            "quota_reset_to_pages": 100000,
            "post_quota_retry_passed": True,
            "post_quota_retry_rows": retry_count,
            "post_quota_retry_integrity": retry_integrity,
            "production_workpool_verified": False,
            "limits": (
                "PRAGMA max_page_count triggers a real SQLite page-quota "
                "SQLITE_FULL with a private retry, not OS ENOSPC, shared filesystem, "
                "or live WorkPool failure. No production data was used."
            ),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="PRIVATE SQLITE_FULL rollback acceptance; no database path."
    )
    parser.add_argument("--rows", type=int, default=500)
    parser.add_argument("--repeat", type=int, default=200)
    args = parser.parse_args(argv)
    try:
        result = run_private_sqlite_full(rows=args.rows, repeat=args.repeat)
    except Exception as error:
        result = {
            "status": "FAIL_OR_BLOCKED", "error_type": type(error).__name__,
            "reason": str(error), "production_workpool_verified": False,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS_SQLITE_FULL_ROLLBACK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
