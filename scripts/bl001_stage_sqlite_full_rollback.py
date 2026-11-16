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
            "production_workpool_verified": False,
            "limits": (
                "PRAGMA max_page_count triggers a real SQLite page-quota "
                "SQLITE_FULL, not an OS ENOSPC, power loss, shared filesystem, "
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
