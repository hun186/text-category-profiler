"""Bounded cross-process SQLite lock/retry acceptance on disposable files only.

Never touches a real WorkPool or accepts an external database path. This tests
lock rejection and recovery after terminating a *lock holder*, not a stage
writer interrupted between table replacement and index creation.
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


_HOLDER = """
import sqlite3
import sys
from pathlib import Path

database = sqlite3.connect(sys.argv[1], timeout=1)
try:
    database.execute("BEGIN EXCLUSIVE")
    Path(sys.argv[2]).write_text("LOCK_ACQUIRED", encoding="ascii")
    sys.stdin.readline()
    database.rollback()
finally:
    database.close()
"""


def _read_verified_rows(path: Path) -> list[tuple[str, str]]:
    """Use a fresh connection to check persisted rows, index and integrity."""
    with closing(sqlite3.connect(path, timeout=3)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise AssertionError("SQLite integrity_check did not return ok")
        columns = {row[1] for row in connection.execute('PRAGMA table_info("sampleSrc")')}
        if not {"text", "label"}.issubset(columns):
            raise AssertionError("sampleSrc text/label columns are missing")
        key_parts = [
            row for row in connection.execute('PRAGMA index_xinfo("text_Index")')
            if row[5] == 1
        ]
        if len(key_parts) != 1 or key_parts[0][1] < 0 or key_parts[0][2] != "text":
            raise AssertionError("text_Index is not a real single-column text index")
        indexes = [row for row in connection.execute('PRAGMA index_list("sampleSrc")')
                   if row[1] == "text_Index"]
        if len(indexes) != 1 or indexes[0][2] or indexes[0][4]:
            raise AssertionError("text_Index is missing, unique, or partial")
        return connection.execute(
            'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()


def _write(path: Path, rows: list[tuple[str, str]]) -> None:
    import pandas as pd

    frame = pd.DataFrame(rows, columns=["text", "label"])
    write_stage_sql(
        str(path), frame, [],
        lambda filename: sqlite3.connect(filename, timeout=0.25),
    )


def _start_holder(path: Path, ready: Path) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(path), str(ready)],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    try:
        while time.monotonic() < deadline:
            if ready.is_file() and ready.read_text(encoding="ascii") == "LOCK_ACQUIRED":
                if process.poll() is not None:
                    raise RuntimeError("Lock holder exited after acquiring the lock")
                return process
            if process.poll() is not None:
                raise RuntimeError("Lock holder exited before acquiring the lock")
            time.sleep(0.05)
        raise RuntimeError("Lock holder did not acquire its exclusive lock")
    except BaseException:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        if process.stdin:
            process.stdin.close()
        if process.stderr:
            process.stderr.close()
        raise


def _stop_holder(process: subprocess.Popen, *, abrupt: bool) -> None:
    try:
        if process.poll() is None:
            if abrupt:
                process.kill()
            else:
                if process.stdin is None:
                    raise AssertionError("Lock holder stdin not available")
                process.stdin.write("\n")
                process.stdin.flush()
            process.wait(timeout=5)
        if not abrupt and process.returncode != 0:
            raise AssertionError("Graceful lock holder did not exit successfully")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stdin:
            process.stdin.close()
        if process.stderr:
            process.stderr.close()


def run_private_lock_acceptance() -> dict:
    """Use two independent child-process lock scenarios and fresh SQLite reads."""
    with tempfile.TemporaryDirectory(prefix="bl001-private-sqlite-lock-") as folder:
        database = Path(folder) / "stage-private.sqlite3"
        current = [("台北", "TW Affairs"), ("桃園", "TW Security")]
        _write(database, current)
        if _read_verified_rows(database) != current:
            raise AssertionError("Initial committed stage rows differ")

        checked = ["initial_write_and_index"]
        for label, abrupt in (("graceful_unlock", False), ("terminated_lock_holder", True)):
            ready = Path(folder) / (label + ".ready")
            holder = _start_holder(database, ready)
            try:
                expected_lock_error = False
                try:
                    _write(database, [("不得覆寫", "TW Blocked")])
                except Exception as error:
                    if "database is locked" not in str(error).lower():
                        raise
                    expected_lock_error = True
                if not expected_lock_error:
                    raise AssertionError("Concurrent write was not rejected by SQLite lock")
            finally:
                _stop_holder(holder, abrupt=abrupt)

            if _read_verified_rows(database) != current:
                raise AssertionError("Failed locked write changed committed rows or schema")
            checked.append(label + "_rejects_write_and_preserves_rows")
            replacement = [("復原後資料", "TW Recovery")] if abrupt else [
                ("正常解鎖", "TW Recovery")
            ]
            _write(database, replacement)
            if _read_verified_rows(database) != replacement:
                raise AssertionError("Retry did not persist the expected rows/index")
            checked.append(label + "_retry_and_index")
            current = replacement
        return {
            "status": "PASS",
            "scope": "private_tempfile_only_no_workpool",
            "checks": checked,
            "limits": "Does not test interrupted stage writer atomicity or live WorkPool",
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Cross-process private SQLite lock/recovery test; NO WorkPool access."
    )
    parser.parse_args(argv)
    try:
        import pandas  # noqa: F401 - fail closed if required dependency is absent
    except ImportError as error:
        print(json.dumps({"status": "BLOCKED_DEPENDENCY", "reason": str(error)}))
        return 2
    try:
        result = run_private_lock_acceptance()
    except (Exception, AssertionError) as error:
        result = {"status": "FAIL", "error_type": type(error).__name__, "reason": str(error)}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
