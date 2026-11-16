"""Private multi-process KI-012 writer overlap and orphan-stage acceptance.

Creates only temporary SQLite databases and never accepts an external DB path.
Kills *only* subprocess writers launched by this diagnostic. A staged candidate
may persist after an abrupt kill: verify it is not confused with sampleSrc and
not silently deleted by another writer. No production WorkPool is touched.
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

from text_category_profiler.data.stage_sql import write_stage_sql


_REPO = Path(__file__).resolve().parents[1]
_CANDIDATE_NAME = re.compile(r"__bl001_stage_[0-9a-f]{32}\Z")
_CHILD = r"""
from pathlib import Path
import sqlite3
import sys
import pandas as pd
from text_category_profiler.data.stage_sql import write_stage_sql

db_path, marker_path, phase = sys.argv[1:]
class PausedWriter(sqlite3.Connection):
    def execute(self, sql, *args, **kwargs):
        stop = ((phase == "before_swap" and sql == "BEGIN IMMEDIATE")
                or (phase == "inside_swap" and
                    sql.startswith('CREATE INDEX "text_Index"')))
        if stop:
            Path(marker_path).write_text(phase, encoding="ascii")
            sys.stdin.readline()
        return super().execute(sql, *args, **kwargs)

frame = pd.DataFrame({"text": ["尚未完成的候選"], "label": ["IN_PROGRESS"]})
write_stage_sql(
    db_path, frame, [],
    lambda path: sqlite3.connect(path, factory=PausedWriter, timeout=2),
)
"""


def _state(path: Path) -> dict:
    with closing(sqlite3.connect(path, timeout=2)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise AssertionError("SQLite integrity_check not ok: " + str(integrity))
        rows = db.execute(
            'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()
        index_keys = [
            entry for entry in db.execute('PRAGMA index_xinfo("text_Index")')
            if entry[5] == 1
        ]
        if (len(index_keys) != 1 or index_keys[0][2] != "text"
                or index_keys[0][1] < 0):
            raise AssertionError("text_Index no longer indexes the real text column")
        pandas_indexes = [
            entry[1] for entry in db.execute('PRAGMA index_list("sampleSrc")')
        ]
        if set(pandas_indexes) != {"text_Index", "ix_sampleSrc_index"}:
            raise AssertionError("sampleSrc pandas indexes changed: " + str(pandas_indexes))
        candidates = sorted(
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) if _CANDIDATE_NAME.fullmatch(row[0])
        )
        return {"rows": rows, "candidate_names": candidates,
                "index_integrity": True, "sqlite_integrity": "ok"}


def _write(path: Path, text: str, label: str) -> None:
    import pandas as pd

    frame = pd.DataFrame({"text": [text], "label": [label]})
    write_stage_sql(
        str(path), frame, [],
        lambda name: sqlite3.connect(name, timeout=0.35),
    )


def _start_paused(path: Path, marker: Path, phase: str) -> subprocess.Popen:
    process = subprocess.Popen(
        [sys.executable, "-c", _CHILD, str(path), str(marker), phase],
        cwd=_REPO, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, text=True,
    )
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if marker.is_file() and marker.read_text(encoding="ascii") == phase:
                if process.poll() is not None:
                    raise RuntimeError("Paused writer exited unexpectedly")
                return process
            if process.poll() is not None:
                diagnostic = process.stderr.read()[-800:] if process.stderr else ""
                raise RuntimeError("Writer exited before pause: " + diagnostic)
            time.sleep(0.05)
        raise RuntimeError("Writer did not reach pause point")
    except BaseException:
        _kill_and_close(process)
        raise


def _kill_and_close(process: subprocess.Popen) -> None:
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        if process.stdin:
            process.stdin.close()
        if process.stderr:
            process.stderr.close()


def _require_rows(state: dict, expected: list[tuple[str, str]]) -> None:
    if state["rows"] != expected:
        raise AssertionError("Unexpected committed sampleSrc rows: " + str(state["rows"]))


def run_private_overlap_acceptance() -> dict:
    """Check a pre-transaction overlap and a locked in-transaction interruption."""
    with tempfile.TemporaryDirectory(prefix="ki012-overlap-private-") as folder:
        root = Path(folder)
        checks = []

        # Writer A is paused with its candidate committed but no final lock.
        # Writer B can safely publish; killing A must not lose B's output.
        path = root / "before-swap.sqlite3"
        _write(path, "既有資料", "OLD")
        writer_a = _start_paused(path, root / "before.marker", "before_swap")
        try:
            staged = _state(path)
            _require_rows(staged, [("既有資料", "OLD")])
            if len(staged["candidate_names"]) != 1:
                raise AssertionError("Expected a single active staging table")
            _write(path, "第二程序成功", "WINNER")
            _require_rows(_state(path), [("第二程序成功", "WINNER")])
            checks.append("overlap_before_swap_other_writer_commits")
        finally:
            _kill_and_close(writer_a)

        after_kill = _state(path)
        _require_rows(after_kill, [("第二程序成功", "WINNER")])
        if after_kill["candidate_names"] != staged["candidate_names"]:
            raise AssertionError("Killed writer's candidate was unexpectedly modified")
        checks.append("killed_pre_swap_preserves_winner_and_reports_candidate")

        _write(path, "第三程序恢復", "RETRY")
        recovered = _state(path)
        _require_rows(recovered, [("第三程序恢復", "RETRY")])
        if recovered["candidate_names"] != after_kill["candidate_names"]:
            raise AssertionError("Retry deleted a candidate owned by another writer")
        checks.append("subsequent_writer_does_not_delete_unowned_candidate")

        # Writer A has acquired its final transaction lock and is paused after
        # rebuilding the table, before committing text_Index. A concurrent
        # writer must fail with locked, never silently modify the old output.
        locked_path = root / "during-swap.sqlite3"
        _write(locked_path, "交易前原始", "OLD")
        writer_a = _start_paused(
            locked_path, root / "inside.marker", "inside_swap"
        )
        try:
            locked = False
            try:
                _write(locked_path, "不准提交", "BLOCKED")
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower():
                    raise
                locked = True
            if not locked:
                raise AssertionError("Competing writer did not respect SQLite lock")
            checks.append("overlap_inside_swap_competing_writer_rejected")
        finally:
            _kill_and_close(writer_a)

        interrupted = _state(locked_path)
        _require_rows(interrupted, [("交易前原始", "OLD")])
        if len(interrupted["candidate_names"]) != 1:
            raise AssertionError("Expected killed writer's orphan candidate only")
        checks.append("killed_mid_swap_rolls_back_sampleSrc_and_index")

        _write(locked_path, "解鎖後重試", "RECOVERY")
        retry = _state(locked_path)
        _require_rows(retry, [("解鎖後重試", "RECOVERY")])
        if retry["candidate_names"] != interrupted["candidate_names"]:
            raise AssertionError("Recovery changed the killed writer's candidate")
        checks.append("post_rollback_retry_preserves_existing_candidate")

        return {
            "status": "PASS",
            "scope": "private_tempfile_only_no_workpool",
            "checks": checks,
            "orphan_candidates_after_pre_swap_kill": len(recovered["candidate_names"]),
            "orphan_candidates_after_mid_swap_kill": len(retry["candidate_names"]),
            "limits": ("No auto-cleanup or live-WorkPool guarantee; "
                       "only two controlled overlap points"),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Private SQLite overlap/orphan acceptance; no external DB paths."
    )
    parser.parse_args(argv)
    try:
        import pandas  # noqa: F401 - required runtime integration
    except ImportError as error:
        print(json.dumps({"status": "BLOCKED_DEPENDENCY", "reason": str(error)}))
        return 2
    try:
        outcome = run_private_overlap_acceptance()
    except Exception as error:
        outcome = {"status": "FAIL", "reason": str(error),
                   "error_type": type(error).__name__}
    print(json.dumps(outcome, ensure_ascii=False, sort_keys=True))
    return 0 if outcome["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
