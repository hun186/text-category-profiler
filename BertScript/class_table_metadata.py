"""ClassTable CSV contract, validation, TopicTree audit, and candidate merge.

This module is stdlib-only. TopicTree owns graph edges; ClassTable owns display metadata.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from collections import defaultdict
from pathlib import Path
from tempfile import NamedTemporaryFile

HEADERS = ("ClassLabel", "CT", "Explanation")
DEFAULT_CSV = Path(__file__).with_name("ClassTable.csv")
DEFAULT_TREE = Path(__file__).resolve().parents[1] / "ClassesTree" / "data" / "TopicTree.csv"


class MetadataError(ValueError):
    """Invalid metadata or candidate/graph contract."""


def read_rows(path: str | Path) -> list[dict[str, str]]:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if tuple(reader.fieldnames or ()) != HEADERS:
                raise MetadataError(f"{path}: expected CSV columns {HEADERS}, got {reader.fieldnames}")
            rows = []
            for line_no, row in enumerate(reader, 2):
                if None in row or any(value is None for value in row.values()):
                    raise MetadataError(f"{path}: malformed CSV row near line {line_no}")
                if not row["ClassLabel"] or not row["ClassLabel"].strip():
                    raise MetadataError(f"{path}: blank ClassLabel near line {line_no}")
                if row["ClassLabel"] != row["ClassLabel"].strip():
                    raise MetadataError(f"{path}: surrounding whitespace in ClassLabel {row['ClassLabel']!r}")
                if not row["CT"] or not row["CT"].strip():
                    raise MetadataError(f"{path}: blank CT for {row['ClassLabel']!r}")
                rows.append(row)
    except (csv.Error, UnicodeError) as exc:
        raise MetadataError(f"{path}: invalid CSV: {exc}") from exc
    return rows


def rows_to_table(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    table = {}
    for row in rows:
        label = row["ClassLabel"]
        if label in table:
            raise MetadataError(f"duplicate ClassLabel: {label!r}")
        table[label] = {"CT": row["CT"], "Explanation": row["Explanation"]}
    return table


def load_class_table(path: str | Path = DEFAULT_CSV) -> dict[str, dict[str, str]]:
    """Return existing dict-of-dicts API without changing cwd or machine paths."""
    return rows_to_table(read_rows(path))


def table_to_csv(table: dict[str, dict[str, str]]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(HEADERS)
    for label in sorted(table):
        record = table[label]
        writer.writerow((label, record["CT"], record.get("Explanation", "")))
    return stream.getvalue()


def check_round_trip(table: dict[str, dict[str, str]]) -> None:
    content = table_to_csv(table)
    stream = io.StringIO(content, newline="")
    reader = csv.DictReader(stream, strict=True)
    if tuple(reader.fieldnames or ()) != HEADERS:
        raise MetadataError("CSV serialization lost its column schema")
    recovered = rows_to_table(list(reader))
    normalized = {
        key: {"CT": value["CT"], "Explanation": value.get("Explanation", "")}
        for key, value in table.items()
    }
    if recovered != normalized:
        raise MetadataError("CSV round-trip lost metadata")


def topic_nodes(path: str | Path) -> set[str]:
    """Read union of graph endpoints; note and relation columns are not nodes."""
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = csv.reader(handle, strict=True)
            first = next(rows, None)
            if first is None:
                raise MetadataError(f"{path}: empty TopicTree")
            names = [cell.strip().lstrip("#").casefold() for cell in first[:2]]
            has_header = (
                len(names) >= 2
                and (
                    ("母類別" in names[0] and "子類別" in names[1])
                    or names in (["parent", "child"], ["source", "target"])
                )
            )
            nodes = set()
            iterator = rows if has_header else iter([first, *rows])
            for i, row in enumerate(iterator, 2 if has_header else 1):
                if len(row) < 2:
                    raise MetadataError(f"{path}: graph row {i} has fewer than two columns")
                parent, child = row[0], row[1]
                if not parent or not child:
                    raise MetadataError(f"{path}: empty graph endpoint near row {i}")
                # Preserve raw labels; one current graph endpoint has trailing whitespace.
                # Such anomalies are surfaced as set differences, not fatal graph errors.
                nodes.update((parent, child))
    except (csv.Error, UnicodeError) as exc:
        raise MetadataError(f"{path}: invalid graph CSV: {exc}") from exc
    return nodes


def audit(table: dict[str, dict[str, str]], tree_path: str | Path | None = None) -> dict:
    by_ct = defaultdict(list)
    for label, value in table.items():
        by_ct[value["CT"]].append(label)
    result = {
        "ClassTableRows": len(table),
        "DuplicateClassLabel": [],
        "DuplicateCT": {key: sorted(labels) for key, labels in sorted(by_ct.items())
                        if len(labels) > 1},
    }
    if tree_path is not None:
        nodes = topic_nodes(tree_path)
        result.update({
            "TopicTreeNodes": len(nodes),
            "MissingInClassTable": sorted(nodes - table.keys()),
            "OrphanInClassTable": sorted(table.keys() - nodes),
        })
    return result


def atomic_write(path: str | Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8-sig", newline="",
                                dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
                                delete=False) as handle:
            temp = Path(handle.name)
            handle.write(content)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def merge_candidates(
    base_table: dict[str, dict[str, str]],
    old_tree_path: str | Path,
    added_edges_path: str | Path,
    candidates_path: str | Path,
) -> tuple[dict[str, dict[str, str]], set[str]]:
    """Require candidates == (all added-edge nodes - original-tree nodes)."""
    old_nodes = topic_nodes(old_tree_path)
    new_nodes = topic_nodes(added_edges_path) - old_nodes
    candidate_table = load_class_table(candidates_path)
    missing, extra = new_nodes - candidate_table.keys(), candidate_table.keys() - new_nodes
    if missing or extra:
        raise MetadataError(
            f"candidate mismatch: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    already_present = new_nodes & base_table.keys()
    if already_present:
        raise MetadataError(f"new graph labels already in ClassTable: {sorted(already_present)}")
    merged = dict(base_table)
    merged.update(candidate_table)
    check_round_trip(merged)
    return merged, new_nodes



def check_active_consumers(paths: tuple[Path, ...] | None = None) -> None:
    """Refuse retired metadata spelling in maintained visualization consumers."""
    if paths is None:
        base = Path(__file__).parent
        paths = (
            base / "Test_result_Vis.py",
            base / "Test_result_Vis_layout.py",
            base / "VisParameters_Format.py",
        )
    # The standalone historical copy and AST migration helper are NOT consumers.
    legacy_name = "Explain" + "ation"
    for path in paths:
        if legacy_name in path.read_text(encoding="utf-8"):
            raise MetadataError(f"{path}: active code still uses retired metadata key")



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate/merge ClassTable CSV metadata")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    validate.add_argument("--topic-tree", type=Path, default=DEFAULT_TREE)
    validate.add_argument("--strict-tree", action="store_true")
    validate.add_argument("--json", action="store_true")
    merge = sub.add_parser("merge")
    merge.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    merge.add_argument("--base-tree", required=True, type=Path)
    merge.add_argument("--edges", required=True, type=Path)
    merge.add_argument("--candidates", required=True, type=Path)
    merge.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        table = load_class_table(args.csv)
        check_round_trip(table)
        if args.command == "validate":
            check_active_consumers()
            report = audit(table, args.topic_tree)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print(f"ClassTable: {report['ClassTableRows']} rows; "
                      f"TopicTree: {report['TopicTreeNodes']} nodes")
                for key in ("DuplicateCT", "MissingInClassTable", "OrphanInClassTable"):
                    print(f"WARNING {key}: {len(report[key])}")
            return 1 if args.strict_tree and (
                report["MissingInClassTable"] or report["OrphanInClassTable"]
            ) else 0
        result, nodes = merge_candidates(
            table, args.base_tree, args.edges, args.candidates
        )
        atomic_write(args.output, table_to_csv(result))
        print(f"Merged {len(nodes)} new graph nodes into {args.output}; "
              f"total ClassTable rows={len(result)}")
        return 0
    except (MetadataError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
