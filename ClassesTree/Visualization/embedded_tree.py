"""Bounded taxonomy graph data for an opt-in, same-port Dash viewer.

No Dash, Jaal, pandas, networkx, browser or graph traversal runs at import.
This view preserves directed TopicTree endpoints, including non-"contains"
relations; it does not modify the authoritative taxonomy.
"""
from __future__ import annotations

import csv
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from BertScript.class_table_metadata import load_class_table

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TOPIC_FILES = (DATA_DIR / "TopicTree.csv", DATA_DIR / "TopicTree_AK4.csv")
DEFAULT_MAX_NODES = 150
MAX_SUBGRAPH_NODES = 1000
MAX_FULL_NODES = 4000
MAX_FULL_EDGES = 8000


class GraphLimitError(ValueError):
    """The requested graph exceeds a deliberate resource guard."""


@lru_cache(maxsize=4)
def _read_edges(file_tokens):
    edges = []
    seen = set()
    for filename, _mtime_ns, _size in file_tokens:
        with open(filename, "r", encoding="utf-8-sig", newline="") as stream:
            for lineno, row in enumerate(csv.reader(stream, strict=True), 1):
                if not row or len(row) < 3:
                    continue
                parent, child = row[0].strip(), row[1].strip()
                if lineno == 1 and parent.lstrip("#") in ("母類別", "Parent"):
                    continue
                if not parent or not child or parent.startswith("#"):
                    continue
                edge = (parent, child)
                if edge not in seen:
                    seen.add(edge)
                    edges.append(edge)
    nodes = tuple(sorted({node for edge in edges for node in edge}))
    adjacency = defaultdict(list)
    for parent, child in edges:
        adjacency[parent].append(child)
    return tuple(edges), nodes, dict(adjacency)


def load_graph(files=TOPIC_FILES):
    """Stat tracked taxonomy paths on demand; cache by file state, not CWD."""
    tokens = tuple(
        (str(Path(filename).resolve()), Path(filename).stat().st_mtime_ns,
         Path(filename).stat().st_size)
        for filename in files
    )
    return _read_edges(tokens)


def draw_graph(root="TW Affairs", depth=2, max_nodes=DEFAULT_MAX_NODES,
               *, full=False, existing_nodes=(), files=TOPIC_FILES,
               metadata=None):
    """Return bounded Cytoscape elements only after an explicit user action.

    Non-full requests are directed breadth-first subtrees, optionally merging
    the previous view for deliberate expansion. Full graph is opt-in and has
    separate, explicit maximum node/edge guards.
    """
    edges, nodes, adjacency = load_graph(files)
    if full:
        if len(nodes) > MAX_FULL_NODES or len(edges) > MAX_FULL_EDGES:
            raise GraphLimitError(
                f"全圖有 {len(nodes)} 節點、{len(edges)} 關係，超過安全限制 "
                f"({MAX_FULL_NODES} 節點／{MAX_FULL_EDGES} 關係)；請選子樹。"
            )
        selected = set(nodes)
        truncated = False
    else:
        if not isinstance(root, str) or not root.strip():
            raise ValueError("請先輸入類別名稱。")
        root = root.strip()
        if root not in set(nodes):
            raise ValueError(f"找不到類別：{root}（請輸入正確英文 ClassLabel）。")
        if type(depth) is not int or not 1 <= depth <= 5:
            raise ValueError("展開深度只能是 1～5。")
        if type(max_nodes) is not int or not 1 <= max_nodes <= MAX_SUBGRAPH_NODES:
            raise ValueError(f"節點上限必須介於 1～{MAX_SUBGRAPH_NODES}。")
        selected = set(existing_nodes)
        if len(selected) > max_nodes:
            raise GraphLimitError("現有節點已超出選定上限；請先清空或調高上限。")
        selected.add(root)
        queue = deque([(root, 0)])
        explored = set()
        truncated = False
        while queue:
            parent, level = queue.popleft()
            if parent in explored or level >= depth:
                continue
            explored.add(parent)
            for child in adjacency.get(parent, ()):
                if child not in selected:
                    if len(selected) >= max_nodes:
                        truncated = True
                        continue
                    selected.add(child)
                if child not in explored:
                    queue.append((child, level + 1))

    chosen_edges = [(src, dst) for src, dst in edges
                    if src in selected and dst in selected]
    if metadata is None:
        metadata = load_class_table()
    node_elements = [
        {"data": {"id": node, "label": node,
                  "ct": metadata.get(node, {}).get("CT", ""),
                  "root": bool(not full and node == root)},
         "classes": "tree-root" if not full and node == root else ""}
        for node in sorted(selected)
    ]
    edge_elements = [
        {"data": {"id": f"tree-edge-{i}", "source": src, "target": dst}}
        for i, (src, dst) in enumerate(chosen_edges)
    ]
    return {
        "elements": node_elements + edge_elements,
        "nodes": len(selected),
        "edges": len(chosen_edges),
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "truncated": truncated,
        "full": full,
    }
