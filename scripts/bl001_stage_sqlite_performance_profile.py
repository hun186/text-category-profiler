"""Bounded private-disk performance profile for the KI-012 stage writer.

A measurement, not a benchmark claim, optimization, SLA or permission to
operate on real WorkPool. All databases are created in TemporaryDirectory and
removed automatically. No user-selectable database path or deletion.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from time import perf_counter

from text_category_profiler.data.stage_sql import write_stage_sql


def _validate(rows: int, rounds: int) -> None:
    if not 1 <= rows <= 20000:
        raise ValueError("rows must be between 1 and 20000")
    if not 1 <= rounds <= 3:
        raise ValueError("rounds must be between 1 and 3")


def profile_private_writers(*, rows: int = 1000, rounds: int = 2) -> dict:
    """Compare serial legacy and atomic writes on separate disposable SQLite DBs."""
    _validate(rows, rounds)
    import pandas as pd

    # Deliberately bounded in both row count and text length.
    frame = pd.DataFrame({
        "text": [f"中文分類_{i:05d}_樣本內容" * 4 for i in range(rows)],
        "label": [f"TOPIC_{i % 7}" for i in range(rows)],
    })
    with tempfile.TemporaryDirectory(prefix="ki012-private-perf-") as temp:
        databases = {
            "legacy_two_step": Path(temp) / "legacy.sqlite3",
            "atomic_staging": Path(temp) / "atomic.sqlite3",
        }
        timings = {}
        sizes = {}
        for kind, path in databases.items():
            samples = []
            for _ in range(rounds):
                start = perf_counter()
                if kind == "legacy_two_step":
                    # Only uses a private copy to characterize the legacy
                    # cost. This path is NOT deployed, endorsed or crash-safe.
                    with closing(sqlite3.connect(path)) as cnx:
                        frame.to_sql(
                            name="sampleSrc", con=cnx, if_exists="replace"
                        )
                        cnx.execute(
                            'CREATE INDEX "text_Index" ON "sampleSrc"("text")'
                        )
                        cnx.commit()
                else:
                    write_stage_sql(str(path), frame, [], sqlite3.connect)
                samples.append(round(perf_counter() - start, 6))
            with closing(sqlite3.connect(path)) as cnx:
                count = cnx.execute(
                    'SELECT COUNT(*) FROM "sampleSrc"'
                ).fetchone()[0]
                key = [
                    item for item in cnx.execute(
                        'PRAGMA index_xinfo("text_Index")'
                    ) if item[5] == 1
                ]
                integrity = cnx.execute("PRAGMA integrity_check").fetchone()[0]
                orphan_count = cnx.execute(
                    "SELECT COUNT(*) FROM sqlite_master "
                    "WHERE type='table' AND name LIKE '__bl001_stage_%'"
                ).fetchone()[0]
                if (count != rows or integrity != "ok" or orphan_count
                        or len(key) != 1 or key[0][2] != "text"
                        or key[0][1] < 0):
                    raise AssertionError(
                        "Private SQLite row/index/integrity check failed"
                    )
            timings[kind] = samples
            sizes[kind] = path.stat().st_size

        atomic_mean = sum(timings["atomic_staging"]) / rounds
        legacy_mean = sum(timings["legacy_two_step"]) / rounds
        return {
            "status": "PASS_MEASURED",
            "scope": "private_tempfile_only_no_workpool",
            "rows": rows,
            "rounds": rounds,
            "elapsed_seconds": timings,
            "db_file_bytes": sizes,
            "atomic_vs_legacy_elapsed_ratio": round(
                atomic_mean / legacy_mean, 3
            ) if legacy_mean > 0 else None,
            "limitations": (
                "Short local serial writes only; numbers are environment-specific. "
                "No peak disk use, network share, live WorkPool, concurrent load, "
                "large model pipeline, or performance SLA inferred."
            ),
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded PRIVATE SQLite writer timing; no DB path accepted."
    )
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--rounds", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        data = profile_private_writers(rows=args.rows, rounds=args.rounds)
    except (Exception, AssertionError) as error:
        data = {
            "status": "FAIL_OR_BLOCKED",
            "error_type": type(error).__name__,
            "reason": str(error),
        }
    print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return 0 if data["status"] == "PASS_MEASURED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
