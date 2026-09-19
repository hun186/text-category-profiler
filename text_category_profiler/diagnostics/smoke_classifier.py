"""Deterministic test-only replacement for the model inference child."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Sequence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-ts", "--test")
    parser.add_argument("-mdlDir", "--modelDir")
    parser.add_argument(
        "-BertDataDir", "--BertDatasetSubDir", required=True, dest="dataset_dir"
    )
    parser.add_argument("-mdlType", "--ModelType")
    parser.add_argument("-ZeroShot", "--ActiveHTCZeroshot")
    parser.add_argument("-MaxSeqLen", "--MaxSeqLength")
    parser.add_argument("-SaveOptimizer", "--SaveOptimizer")
    return parser


def _read_labels(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"smoke label metadata does not exist: {path}")
    labels = sorted({line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()})
    if not labels:
        raise ValueError(f"smoke label metadata is empty: {path}")
    return labels


def main(argv: Sequence[str] | None = None) -> int:
    args, unknown = _parser().parse_known_args(argv)
    dataset_dir = Path(args.dataset_dir).resolve()
    database = dataset_dir / "test.sql3"
    if not database.is_file():
        raise FileNotFoundError(f"smoke test database does not exist: {database}")

    labels = _read_labels(dataset_dir / "TopicAnalysis_LabelList.txt")
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            "SELECT OutLabel, text FROM sampleSrc ORDER BY rowid"
        ).fetchall()
    if not rows:
        raise ValueError(f"smoke test database has no sampleSrc rows: {database}")

    label_set = set(labels)
    predictions = [
        out_label if out_label in label_set else labels[index % len(labels)]
        for index, (out_label, _text) in enumerate(rows)
    ]
    (dataset_dir / "test_results.tsv").write_text(
        "".join(f"{label}\n" for label in predictions), encoding="utf-8"
    )

    marker_value = os.environ.get("TCP_SMOKE_CLASSIFIER_MARKER")
    if marker_value:
        marker = Path(marker_value)
        marker.parent.mkdir(parents=True, exist_ok=True)
        with marker.open("a", encoding="utf-8") as marker_file:
            marker_file.write(
                json.dumps(
                    {
                        "dataset_dir": str(dataset_dir),
                        "row_count": len(rows),
                        "unknown_args": unknown,
                    },
                    sort_keys=True,
                )
                + "\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
