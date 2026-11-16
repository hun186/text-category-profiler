"""KI-012 bounded disk checkpoint profile on a PRIVATE disposable SQLite DB.

Measure stage-candidate, transaction and journal sidecars at selected SQL
boundaries. NOT a continuously sampled disk high-water mark, quota acceptance,
production WorkPool approval, or full OS free-space accounting.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile

from text_category_profiler.data.stage_sql import write_stage_sql


def _on_disk(path: Path) -> dict[str, int]:
    """Only fixed SQLite files alongside the generated private DB."""
    names = {
        "db": path,
        "journal": Path(str(path) + "-journal"),
        "wal": Path(str(path) + "-wal"),
        "shm": Path(str(path) + "-shm"),
    }
    sizes = {name: f.stat().st_size if f.is_file() else 0
             for name, f in names.items()}
    sizes["total"] = sum(sizes.values())
    return sizes


class _CheckpointConnection(sqlite3.Connection):
    """Observe stages without changing the shared production writer."""

    def attach(self, output: list[dict]) -> None:
        self._observations = output
        self._db_path = Path(self.execute("PRAGMA database_list").fetchone()[2])
        self._swap_started = False

    def _record(self, stage: str) -> None:
        if hasattr(self, "_observations"):
            self._observations.append({"stage": stage, **_on_disk(self._db_path)})

    def execute(self, sql, *args, **kwargs):
        if sql.startswith("BEGIN IMMEDIATE"):
            self._record("candidate_ready")
        value = super().execute(sql, *args, **kwargs)
        if sql.startswith("BEGIN IMMEDIATE"):
            self._swap_started = True
        elif sql.startswith('INSERT INTO "sampleSrc" SELECT'):
            self._record("after_copy")
        elif sql.startswith('CREATE INDEX "text_Index"'):
            self._record("after_text_index")
        elif sql.startswith('DROP TABLE "__bl001_stage_'):
            self._record("candidate_dropped_uncommitted")
        return value

    def commit(self):
        if getattr(self, "_swap_started", False):
            self._record("before_swap_commit")
        result = super().commit()
        if getattr(self, "_swap_started", False):
            self._record("after_swap_commit")
            self._swap_started = False
        return result


def profile_private_disk(*, rows: int = 2000, repeat: int = 4) -> dict:
    if not 10 <= rows <= 20000 or not 1 <= repeat <= 8:
        raise ValueError("Bounds: rows 10..20000, repeat 1..8")
    import pandas as pd

    # Deliberately cap the per-row payload to bound temporary memory and IO.
    with tempfile.TemporaryDirectory(prefix="ki012-private-disk-") as root:
        path = Path(root) / "profile.sqlite3"
        seed = pd.DataFrame({
            "text": [("舊分類_" + str(i)) * repeat for i in range(rows)],
            "label": ["old"] * rows,
        })
        frame = pd.DataFrame({
            "text": [("新分類_" + str(i)) * repeat for i in range(rows)],
            "label": ["new"] * rows,
        })
        write_stage_sql(str(path), seed, [], sqlite3.connect)
        initial = _on_disk(path)
        phases: list[dict] = []

        def monitored_connect(filename: str):
            connection = sqlite3.connect(filename, factory=_CheckpointConnection)
            connection.attach(phases)
            return connection

        write_stage_sql(str(path), frame, [], monitored_connect)
        phases.append({"stage": "closed_final", **_on_disk(path)})
        stages = {entry["stage"] for entry in phases}
        required = {
            "candidate_ready", "after_copy", "after_text_index",
            "candidate_dropped_uncommitted", "before_swap_commit",
            "after_swap_commit", "closed_final",
        }
        if not required.issubset(stages):
            raise AssertionError("Missing transaction checkpoints: "
                                 + ", ".join(sorted(required - stages)))
        with closing(sqlite3.connect(path)) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise AssertionError("SQLite integrity check failed")
            if db.execute('SELECT COUNT(*) FROM "sampleSrc"').fetchone()[0] != rows:
                raise AssertionError("Final row count mismatch")
            if db.execute('SELECT COUNT(*) FROM "sampleSrc" WHERE label="new"').fetchone()[0] != rows:
                raise AssertionError("Final result contains old or partial rows")
            keys = [r[2] for r in db.execute('PRAGMA index_xinfo("text_Index")')
                    if r[5] == 1]
            if keys != ["text"]:
                raise AssertionError("text_Index no longer matches text")
            table_names = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )]
            if any(name.startswith("__bl001_stage_") for name in table_names):
                raise AssertionError("Candidate table remained after success")
        max_total = max(item["total"] for item in phases)
        final_size = phases[-1]["total"]
        return {
            "status": "PASS_CHECKPOINT_MEASURED",
            "scope": "private_tempfile_only_no_workpool",
            "rows": rows,
            "text_repeat": repeat,
            "initial_disk_bytes": initial,
            "phase_disk_bytes": phases,
            "checkpoint_max_total_bytes": max_total,
            "closed_final_total_bytes": final_size,
            "checkpoint_max_to_final_ratio": round(max_total / final_size, 3)
            if final_size else None,
            "production_workpool_verified": False,
            "limits": (
                "Selected SQL-stage file-size samples, not true peak or available "
                "free-space/quota proof. No network disk, concurrent workers, "
                "crash residue, model pipeline or production WorkPool."
            ),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Private SQLite disk checkpoint profile; no external DB path.")
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--repeat", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        result = profile_private_disk(rows=args.rows, repeat=args.repeat)
    except Exception as exc:
        result = {"status": "FAIL_OR_BLOCKED", "error_type": type(exc).__name__,
                  "reason": str(exc), "production_workpool_verified": False}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS_CHECKPOINT_MEASURED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
