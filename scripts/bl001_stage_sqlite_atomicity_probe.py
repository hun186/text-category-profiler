"""Private-only interruption probe for the fixed Stage-local SQLite writer.

Only uses a temporary database. A child writer is killed after pandas returns
from replacing sampleSrc but before the fixed text_Index CREATE statement.
This intentionally diagnoses a known transaction gap; it never accepts a
WorkPool or user-selected database path.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from text_category_profiler.data.stage_sql import write_stage_sql


_CHILD = r'''
from pathlib import Path
import sqlite3
import sys
import pandas as pd
from text_category_profiler.data.stage_sql import write_stage_sql

class PauseBeforeIndex(sqlite3.Connection):
    def execute(self, sql, *args):
        if sql.lstrip().startswith('CREATE INDEX "text_Index"'):
            Path(sys.argv[2]).write_text('AFTER_REPLACE_BEFORE_INDEX', encoding='ascii')
            sys.stdin.readline()
        return super().execute(sql, *args)

frame = pd.DataFrame({'text': ['中斷時新資料'], 'label': ['TW Interrupted']})
write_stage_sql(
    sys.argv[1], frame, [],
    lambda name: sqlite3.connect(name, factory=PauseBeforeIndex, timeout=1),
)
'''


def _state(path: Path) -> dict:
    with closing(sqlite3.connect(path, timeout=3)) as cnx:
        if cnx.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise RuntimeError("SQLite integrity_check did not return ok")
        table = cnx.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sampleSrc'"
        ).fetchone()
        if table is None:
            return {"table_present": False, "rows": [], "text_index": False}
        columns = [row[1] for row in cnx.execute('PRAGMA table_info("sampleSrc")')]
        if not {"text", "label"}.issubset(columns):
            return {"table_present": True, "rows": [], "text_index": False}
        rows = cnx.execute(
            'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()
        indices = cnx.execute('PRAGMA index_list("sampleSrc")').fetchall()
        present = any(entry[1] == "text_Index" for entry in indices)
        keys = ([row[2] for row in cnx.execute('PRAGMA index_xinfo("text_Index")')
                 if row[5] == 1] if present else [])
        return {"table_present": True, "rows": rows,
                "text_index": present and keys == ["text"]}


def run_probe() -> dict:
    """Diagnose one crash point; PASS means original committed state survives."""
    import pandas as pd

    with tempfile.TemporaryDirectory(prefix="bl001-private-abort-writer-") as folder:
        root = Path(folder)
        database = root / "stage.sqlite3"
        marker = root / "paused.marker"
        frame = pd.DataFrame({"text": ["原始資料"], "label": ["TW Original"]})
        write_stage_sql(str(database), frame, [], sqlite3.connect)
        before = _state(database)
        expected = {"table_present": True,
                    "rows": [("原始資料", "TW Original")], "text_index": True}
        if before != expected:
            raise RuntimeError("Initial committed stage baseline was not valid")

        process = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(database), str(marker)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True,
        )
        try:
            deadline = time.monotonic() + 30
            reached = False
            while time.monotonic() < deadline:
                if (marker.is_file() and
                        marker.read_text(encoding="ascii") == "AFTER_REPLACE_BEFORE_INDEX"):
                    if process.poll() is not None:
                        raise RuntimeError("Writer exited after pause marker")
                    reached = True
                    break
                if process.poll() is not None:
                    error_tail = process.stderr.read()[-600:] if process.stderr else ""
                    raise RuntimeError("Writer stopped before index hook: " + error_tail)
                time.sleep(0.05)
            if not reached:
                raise RuntimeError("Writer never reached after-replace hook")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
            if process.stdin:
                process.stdin.close()
            if process.stderr:
                process.stderr.close()

        after = _state(database)
        original_preserved = after == before
        return {
            "status": "PASS_ATOMICITY" if original_preserved else "FAIL_ATOMICITY",
            "scope": "private_tempfile_only_no_workpool",
            "interruption": "writer_killed_after_replace_before_index",
            "original_preserved": original_preserved,
            "new_partial_rows_present": any(
                text == "中斷時新資料" for text, _ in after["rows"]
            ),
            "text_index_present": after["text_index"],
            "integrity_check": "ok",
            "limits": "One controlled interruption point; not live WorkPool or all crash phases",
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Private interrupted-writer SQLite atomicity probe; no external path."
    )
    parser.parse_args(argv)
    try:
        result = run_probe()
    except Exception as error:
        result = {"status": "BLOCKED_DIAGNOSTIC",
                  "error_type": type(error).__name__, "reason": str(error)}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["status"] == "PASS_ATOMICITY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
