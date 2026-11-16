"""Private SQLite reader-snapshot vs atomic writer cross-process acceptance.

Uses a new TemporaryDirectory SQLite only. A reader holds a transaction while
the real atomic stage writer prepares/attempts its final swap. This is NOT
a production WorkPool, network-disk, or all-reader-interleavings guarantee.
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


_CHILD = r"""
import json
from pathlib import Path
import sqlite3
import sys
import time
import pandas as pd
from text_category_profiler.data.stage_sql import write_stage_sql

db_path, ready, release, inside, outcome, row_count = sys.argv[1:]

class GatedConnection(sqlite3.Connection):
    def execute(self, statement, *args, **kwargs):
        if statement.startswith("BEGIN IMMEDIATE"):
            Path(ready).write_text("candidate_ready", encoding="ascii")
            deadline = time.monotonic() + 15
            while not Path(release).is_file():
                if time.monotonic() >= deadline:
                    raise RuntimeError("reader handoff gate timed out")
                time.sleep(0.02)
        result = super().execute(statement, *args, **kwargs)
        if statement.startswith('DROP TABLE "__bl001_stage_'):
            Path(inside).write_text("about_to_commit", encoding="ascii")
        return result

try:
    frame = pd.DataFrame({
        "text": [f"新資料-{i}" for i in range(int(row_count))],
        "label": ["NEW"] * int(row_count),
    })
    write_stage_sql(
        db_path, frame, [],
        lambda name: sqlite3.connect(name, timeout=12, factory=GatedConnection),
    )
    Path(outcome).write_text(json.dumps({"status": "COMMITTED"}), encoding="ascii")
except Exception as error:
    Path(outcome).write_text(json.dumps({
        "status": "FAIL", "error_type": type(error).__name__
    }), encoding="ascii")
    raise
"""


def _until(path: Path, child: subprocess.Popen, *, seconds: float = 20) -> None:
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        if path.is_file():
            return
        if child.poll() is not None:
            raise RuntimeError("Writer exited before signal: " + path.name)
        time.sleep(0.03)
    raise TimeoutError("Writer did not reach signal: " + path.name)


def private_reader_snapshot(*, rows: int = 40) -> dict:
    if not 10 <= rows <= 500:
        raise ValueError("rows must be 10..500")
    import pandas as pd

    with tempfile.TemporaryDirectory(prefix="ki012-reader-snapshot-private-") as tmp:
        root = Path(tmp)
        db = root / "snapshot.sqlite3"
        initial = pd.DataFrame({
            "text": [f"舊資料-{i}" for i in range(rows)],
            "label": ["OLD"] * rows,
        })
        write_stage_sql(str(db), initial, [], sqlite3.connect)
        with closing(sqlite3.connect(db)) as cnx:
            cnx.execute('CREATE VIEW "source_view" AS SELECT text FROM sampleSrc')
            cnx.commit()

        ready, go = root / "candidate.ready", root / "go.signal"
        inside, outcome = root / "commit.ready", root / "writer.result.json"
        proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD, str(db), str(ready),
             str(go), str(inside), str(outcome), str(rows)],
            cwd=Path(__file__).resolve().parents[1],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True,
        )
        reader = None
        try:
            _until(ready, proc)
            reader = sqlite3.connect(db, timeout=5)
            reader.execute("BEGIN")
            before = reader.execute(
                'SELECT text, label FROM sampleSrc ORDER BY "index"'
            ).fetchall()
            expected = [(f"舊資料-{i}", "OLD") for i in range(rows)]
            if before != expected:
                raise AssertionError("Old reader snapshot does not match seed")

            go.write_text("go", encoding="ascii")
            _until(inside, proc)
            # The writer has executed the replacement transaction but has not
            # committed. Reader must still see the original table and view.
            during = reader.execute(
                'SELECT text, label FROM sampleSrc ORDER BY "index"'
            ).fetchall()
            view_during = reader.execute(
                'SELECT text FROM source_view'
            ).fetchall()
            if during != expected or sorted(view_during) != sorted(
                (r[0],) for r in expected
            ):
                raise AssertionError("Reader observed partially swapped data")
            blocked = proc.poll() is None
            if not blocked:
                raise AssertionError("Writer published before reader committed")
            reader.commit()
            reader.close()
            reader = None

            proc.wait(timeout=15)
            if proc.returncode != 0 or not outcome.is_file():
                raise RuntimeError("Writer failed after reader release")
            result = json.loads(outcome.read_text(encoding="ascii"))
            if result.get("status") != "COMMITTED":
                raise AssertionError("Writer not confirmed committed")

            with closing(sqlite3.connect(db)) as cnx:
                after = cnx.execute(
                    'SELECT text, label FROM sampleSrc ORDER BY "index"'
                ).fetchall()
                after_view = cnx.execute(
                    'SELECT text FROM source_view'
                ).fetchall()
                idx = {r[1] for r in cnx.execute('PRAGMA index_list("sampleSrc")')}
                integrity = cnx.execute("PRAGMA integrity_check").fetchone()[0]
                candidates = [
                    r[0] for r in cnx.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ) if r[0].startswith("__bl001_stage_")
                ]
            updated = [(f"新資料-{i}", "NEW") for i in range(rows)]
            if (after != updated or sorted(after_view) != sorted(
                    (r[0],) for r in updated)
                    or idx != {"ix_sampleSrc_index", "text_Index"}
                    or integrity != "ok" or candidates):
                raise AssertionError("Final writer publication is incomplete")
            return {
                "status": "PASS_PRIVATE_READER_SNAPSHOT",
                "scope": "private_tempfile_only_no_workpool",
                "rows": rows,
                "old_snapshot_preserved_during_swap": True,
                "writer_waited_for_reader_release": blocked,
                "new_rows_visible_after_commit": True,
                "dependent_view_consistent": True,
                "text_indexes_present": True,
                "candidate_tables_remaining": 0,
                "production_workpool_verified": False,
                "limits": (
                    "One gated reader/writer interleaving on local disposable "
                    "SQLite, not real WorkPool, network storage, all lock schedules "
                    "or sustained production concurrency."
                ),
            }
        finally:
            if reader is not None:
                reader.rollback()
                reader.close()
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=5)
            if proc.stderr:
                proc.stderr.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Private reader/writer SQLite snapshot test. No --db.")
    parser.add_argument("--rows", type=int, default=40)
    args = parser.parse_args(argv)
    try:
        result = private_reader_snapshot(rows=args.rows)
    except Exception as error:
        result = {"status": "FAIL_OR_BLOCKED",
                  "error_type": type(error).__name__, "reason": str(error),
                  "production_workpool_verified": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS_PRIVATE_READER_SNAPSHOT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
