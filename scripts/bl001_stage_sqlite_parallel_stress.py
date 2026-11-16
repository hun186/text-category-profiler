"""Bounded multi-PROCESS SQLite stage writer stress, private temp DB only.

A finite overlap check, NOT evidence for arbitrary production WorkPool
parallelism, power failures, or network shared filesystems.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time


_CHILD = r"""
import json
from pathlib import Path
import sqlite3
import sys
import time
import pandas as pd
from text_category_profiler.data.stage_sql import write_stage_sql

db, gate, ready, result, task_id, row_count = sys.argv[1:]
Path(ready).write_text("ready", encoding="ascii")
end = time.monotonic() + 15
while not Path(gate).is_file():
    if time.monotonic() >= end:
        Path(result).write_text(json.dumps({"status": "BLOCKED_GATE"}), encoding="utf-8")
        raise SystemExit(2)
    time.sleep(0.02)
try:
    rows = int(row_count)
    frame = pd.DataFrame({
        "text": [f"{task_id}-文章-{i}" for i in range(rows)],
        "label": [task_id] * rows,
    })
    write_stage_sql(
        db, frame, [],
        lambda path: sqlite3.connect(path, timeout=2),
    )
    outcome = {"status": "COMMITTED", "task_id": task_id}
except Exception as error:
    outcome = {"status": "LOCKED" if "database is locked" in str(error).lower()
               else "UNEXPECTED_ERROR", "error_type": type(error).__name__}
Path(result).write_text(json.dumps(outcome), encoding="utf-8")
"""


def _assert_final(path: Path, *, rows: int, committed: set[str]) -> str:
    with closing(sqlite3.connect(path, timeout=3)) as cnx:
        if cnx.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("SQLite integrity not ok")
        data = cnx.execute(
            'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()
        if len(data) != rows:
            raise AssertionError("Incorrect number of committed rows")
        labels = {row[1] for row in data}
        if len(labels) != 1:
            raise AssertionError("Mixed batch labels: partially committed writers")
        winner = labels.pop()
        if winner not in committed:
            raise AssertionError("Visible rows do not correspond to a completed writer")
        if any(row[0] != f"{winner}-文章-{i}" for i, row in enumerate(data)):
            raise AssertionError("Mixed or reordered batch rows")
        idx = {
            row[1] for row in cnx.execute('PRAGMA index_list("sampleSrc")')
        }
        if idx != {"ix_sampleSrc_index", "text_Index"}:
            raise AssertionError("Final sampleSrc index contract changed")
        keys = [
            row for row in cnx.execute('PRAGMA index_xinfo("text_Index")')
            if row[5] == 1
        ]
        if len(keys) != 1 or keys[0][1] < 0 or keys[0][2] != "text":
            raise AssertionError("Index is not bound to text column")
        if cnx.execute('SELECT COUNT(*) FROM "view_text"').fetchone()[0] != rows:
            raise AssertionError("Dependent view cannot read winner")
        remaining = [
            row[0] for row in cnx.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) if re.fullmatch(r"__bl001_stage_[0-9a-f]{32}", row[0])
        ]
        if remaining:
            raise AssertionError("Completed overlapping writers leaked a candidate table")
        return winner


def stress_private_writers(*, workers: int = 3, rounds: int = 2,
                           rows: int = 50) -> dict:
    if not 2 <= workers <= 4 or not 1 <= rounds <= 3 or not 5 <= rows <= 500:
        raise ValueError("Bounds: workers 2-4, rounds 1-3, rows 5-500")
    import pandas as pd

    with tempfile.TemporaryDirectory(prefix="ki012-private-process-stress-") as tmp:
        root = Path(tmp)
        db = root / "stress.sqlite3"
        from text_category_profiler.data.stage_sql import write_stage_sql

        write_stage_sql(
            str(db),
            pd.DataFrame({"text": ["seed"], "label": ["seed"]}),
            [], sqlite3.connect,
        )
        with closing(sqlite3.connect(db)) as cnx:
            cnx.execute(
                'CREATE VIEW "view_text" AS SELECT "text" FROM "sampleSrc"'
            )
            cnx.commit()
        finished = []
        for round_num in range(rounds):
            round_dir = root / f"round-{round_num}"
            round_dir.mkdir()
            gate = round_dir / "go.signal"
            started = []
            processes = []
            try:
                for i in range(workers):
                    task_id = f"r{round_num}-w{i}"
                    ready = round_dir / f"{i}.ready"
                    outcome = round_dir / f"{i}.json"
                    proc = subprocess.Popen(
                        [sys.executable, "-c", _CHILD, str(db), str(gate),
                         str(ready), str(outcome), task_id, str(rows)],
                        cwd=Path(__file__).resolve().parents[1],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE, text=True,
                    )
                    processes.append(proc)
                    started.append((task_id, ready, outcome, proc))

                deadline = time.monotonic() + 20
                while time.monotonic() < deadline and not all(
                    ready.is_file() for _, ready, _, _ in started
                ):
                    if any(proc.poll() is not None for proc in processes):
                        raise RuntimeError("Child exited before gate")
                    time.sleep(0.05)
                if not all(ready.is_file() for _, ready, _, _ in started):
                    raise RuntimeError("Not all children reached the start gate")
                gate.write_text("go", encoding="ascii")
                for proc in processes:
                    proc.wait(timeout=25)

                outcomes = []
                for task_id, _, output, proc in started:
                    if not output.is_file():
                        raise RuntimeError("Child did not produce result: " + task_id)
                    result = json.loads(output.read_text(encoding="utf-8"))
                    if result["status"] not in ("COMMITTED", "LOCKED"):
                        raise AssertionError("Unexpected child result " + str(result))
                    outcomes.append(result)
                committed = {
                    result["task_id"] for result in outcomes
                    if result["status"] == "COMMITTED"
                }
                if not committed:
                    raise AssertionError("No concurrent writer committed")
                winner = _assert_final(db, rows=rows, committed=committed)
                finished.append({
                    "round": round_num + 1, "committed": len(committed),
                    "locked": len(outcomes) - len(committed),
                    "winner": winner,
                })
            finally:
                for proc in processes:
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait(timeout=5)
                    if proc.stderr:
                        proc.stderr.close()
        return {
            "status": "PASS",
            "scope": "private_tempfile_only_no_workpool",
            "workers": workers, "rounds": rounds, "rows_per_writer": rows,
            "completed_rounds": finished,
            "limits": (
                "Finite 2-4 local processes; allows expected SQLite lock errors. "
                "Not network share, production WorkPool or exhaustive interleavings."
            ),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded PRIVATE-process SQLite writer stress; NO database path."
    )
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--rows", type=int, default=50)
    args = parser.parse_args(argv)
    try:
        result = stress_private_writers(
            workers=args.workers, rounds=args.rounds, rows=args.rows
        )
    except Exception as error:
        result = {
            "status": "FAIL_OR_BLOCKED", "error_type": type(error).__name__,
            "reason": str(error),
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
