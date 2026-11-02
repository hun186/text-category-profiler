"""Pure-stdlib, read-only input adapter for directed Jaal topology graphs.

Relationship CSV: headerless FROM,TO or headed parent,child / from,to /
source,target / 母類別,子類別. Further columns are ignored. UTF-8 BOM accepted.
Metadata CSV: ClassLabel,CT or id,label (customizable columns).
Never write back input files or interpret labels as expressions.
"""
from __future__ import annotations

import csv
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path


class GraphInputError(ValueError):
    """A malformed graph, invalid selection or a deliberate size limit."""


@dataclass(frozen=True)
class Graph:
    edges: tuple[tuple[str, str], ...]
    nodes: tuple[str, ...]
    translations: dict[str, str] = field(default_factory=dict)


_HEADER_PAIRS = {
    ("parent", "child"), ("from", "to"), ("source", "target"),
    ("母類別", "子類別"), ("#母類別", "子類別"),
}
MAX_IMPORT_EDGES = 100_000


def _edge_files(files):
    if isinstance(files, (str, Path)):
        files = [files]
    paths = tuple(Path(path) for path in files)
    if not paths:
        raise GraphInputError("Specify at least one relationship CSV.")
    return paths


def load_graph(edge_files, metadata_file=None, *,
               metadata_id_column="ClassLabel", metadata_label_column="CT"):
    """Load literal directed edges and optional display names.

    Duplicate edges are removed in first-seen order. Cycles, multi-parent
    nodes and disconnected components are deliberately retained.
    """
    edges = []
    seen = set()
    for path in _edge_files(edge_files):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            try:
                for line, row in enumerate(csv.reader(handle, strict=True), 1):
                    if not row or all(not value.strip() for value in row):
                        continue
                    if len(row) < 2:
                        raise GraphInputError(f"{path}:{line}: expected two edge columns")
                    parent, child = row[0].strip(), row[1].strip()
                    if line == 1 and (parent.casefold(), child.casefold()) in _HEADER_PAIRS:
                        continue
                    if not parent or not child:
                        raise GraphInputError(f"{path}:{line}: blank edge endpoint")
                    edge = (parent, child)
                    if edge not in seen:
                        edges.append(edge)
                        seen.add(edge)
                        if len(edges) > MAX_IMPORT_EDGES:
                            raise GraphInputError("Source graph exceeds 100000 edges")
            except (csv.Error, UnicodeError) as exc:
                raise GraphInputError(f"{path}: invalid relationship CSV: {exc}") from exc
    if not edges:
        raise GraphInputError("Relationship CSV contains no directed edges")
    nodes = tuple(sorted({name for edge in edges for name in edge}))
    translations = {}
    if metadata_file is not None:
        path = Path(metadata_file)
        with path.open(encoding="utf-8-sig", newline="") as handle:
            try:
                reader = csv.DictReader(handle, strict=True)
                required = {metadata_id_column, metadata_label_column}
                if not required.issubset(reader.fieldnames or ()):
                    raise GraphInputError(
                        f"{path}: metadata needs {metadata_id_column!r} and "
                        f"{metadata_label_column!r} columns"
                    )
                present = set(nodes)
                recorded = set()
                for line, row in enumerate(reader, 2):
                    if None in row or any(value is None for value in row.values()):
                        raise GraphInputError(f"{path}:{line}: malformed metadata row")
                    name = row[metadata_id_column].strip()
                    if name not in present:
                        continue
                    if name in recorded:
                        raise GraphInputError(f"{path}:{line}: duplicate metadata ID {name!r}")
                    recorded.add(name)
                    translated = row[metadata_label_column].strip()
                    if translated:
                        translations[name] = translated
            except (csv.Error, UnicodeError) as exc:
                raise GraphInputError(f"{path}: invalid metadata CSV: {exc}") from exc
    return Graph(tuple(edges), nodes, translations)


def select_subgraph(graph: Graph, root=None, *, max_nodes=250, max_edges=5000):
    """Select reachable descendants, or bounded full graph when root is None.

    Preserve every edge whose endpoints are selected, including DAG cross-links.
    """
    if type(max_nodes) is not int or not 1 <= max_nodes <= 3000:
        raise GraphInputError("max_nodes must be between 1 and 3000")
    if type(max_edges) is not int or not 1 <= max_edges <= 5000:
        raise GraphInputError("max_edges must be between 1 and 5000")
    if root is None:
        selected = set(graph.nodes)
        if len(selected) > max_nodes:
            raise GraphInputError(
                f"Full graph has {len(selected)} nodes; specify --root or "
                f"increase --max-nodes up to 3000"
            )
    else:
        if root not in graph.nodes:
            raise GraphInputError(f"Unknown graph root: {root!r}")
        adjacency = defaultdict(list)
        for parent, child in graph.edges:
            adjacency[parent].append(child)
        selected = {root}
        queue = deque([root])
        while queue:
            for child in adjacency.get(queue.popleft(), ()):
                if child not in selected:
                    if len(selected) >= max_nodes:
                        raise GraphInputError(
                            f"Selected subtree exceeds {max_nodes} nodes; "
                            "choose a narrower --root or increase --max-nodes"
                        )
                    selected.add(child)
                    queue.append(child)
    chosen_edges = tuple((a, b) for a, b in graph.edges
                         if a in selected and b in selected)
    if len(chosen_edges) > max_edges:
        raise GraphInputError(
            f"Selected graph has {len(chosen_edges)} edges; "
            "choose a narrower --root or increase --max-edges"
        )
    return Graph(chosen_edges, tuple(sorted(selected)),
                 {name: value for name, value in graph.translations.items()
                  if name in selected})
