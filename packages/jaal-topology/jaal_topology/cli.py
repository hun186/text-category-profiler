"""Portable, read-only Jaal CSV viewer CLI; no application project imports."""
from __future__ import annotations

import argparse

from .data import GraphInputError, load_graph, select_subgraph


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="View a directed CSV graph with optional Chinese node labels."
    )
    parser.add_argument("--edges", metavar="CSV", action="append", required=True,
                        help="Directed parent/child CSV (repeatable); 2+ columns")
    parser.add_argument("--metadata", metavar="CSV", default=None,
                        help="Optional ClassLabel,CT or custom node-label CSV")
    parser.add_argument("--metadata-id-column", default="ClassLabel",
                        help="Metadata node ID column, default ClassLabel")
    parser.add_argument("--metadata-label-column", default="CT",
                        help="Metadata display label column, default CT")
    parser.add_argument("--root", default=None,
                        help="Select reachable descendants of this exact node ID")
    parser.add_argument("--max-nodes", type=int, default=250,
                        help="Maximum rendered nodes, 1..3000 (default 250)")
    parser.add_argument("--max-edges", type=int, default=5000,
                        help="Maximum rendered edges, 1..5000 (default 5000)")
    parser.add_argument("--port", "-p", type=int, default=8059,
                        help="Local web port, default 8059")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1..65535")
    if not 1 <= args.max_nodes <= 3000 or not 1 <= args.max_edges <= 5000:
        parser.error("Graph limits must be 1..3000 nodes and 1..5000 edges")
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        graph = load_graph(
            args.edges, args.metadata,
            metadata_id_column=args.metadata_id_column,
            metadata_label_column=args.metadata_label_column,
        )
        selected = select_subgraph(
            graph, args.root, max_nodes=args.max_nodes, max_edges=args.max_edges
        )
        if not selected.edges:
            raise GraphInputError(
                "Selected node has no directed relationship to draw; "
                "choose a parent/ancestor with at least one visible edge"
            )
    except (GraphInputError, OSError) as exc:
        print(f"Jaal topology input error: {exc}", file=__import__("sys").stderr)
        return 2

    from .viewer import build_app
    app = build_app(selected, root=args.root)
    print(f"Read-only Jaal topology: http://127.0.0.1:{args.port}/ "
          f"({len(selected.nodes)} nodes, {len(selected.edges)} directed edges)",
          flush=True)
    run = app.run if hasattr(app, "run") else app.run_server
    run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    return 0
