"""Standalone Jaal rendering; independent of Stage 4 and taxonomy utilities.

Uses Jaal's real Search/Filter/Color/Size Dash app. Enriches the graph
with optional display-language and network/hierarchy controls. The full
Stage-4-only collapse animation remains a separate migration milestone.
"""
from __future__ import annotations

from copy import deepcopy
from html import escape as escape_html
from collections import defaultdict, deque

from .data import Graph


def _depths(graph: Graph, root=None):
    adj = defaultdict(list)
    indegree = defaultdict(int)
    for parent, child in graph.edges:
        adj[parent].append(child)
        indegree[child] += 1
    seeds = [root] if root is not None else [
        name for name in graph.nodes if indegree[name] == 0
    ]
    # Disconnected cycles have no zero-indegree root.
    queue = deque((seed, 0) for seed in seeds)
    depths = {}
    while queue:
        name, level = queue.popleft()
        if name in depths:
            continue
        depths[name] = level
        for child in adj.get(name, ()):
            queue.append((child, level + 1))
    for name in graph.nodes:
        if name not in depths:
            queue = deque([(name, 0)])
            while queue:
                node, level = queue.popleft()
                if node in depths:
                    continue
                depths[node] = level
                for child in adj.get(node, ()):
                    queue.append((child, level + 1))
    return depths


def to_jaal_dataframes(graph: Graph, *, root=None):
    """Adapt any two-column directed graph to original Jaal DataFrame columns."""
    import pandas as pd

    depths = _depths(graph, root=root)
    incoming = defaultdict(int)
    outgoing = defaultdict(int)
    for parent, child in graph.edges:
        incoming[child] += 1
        outgoing[parent] += 1
    nodes = pd.DataFrame([
        {
            "id": name,
            "label": name,
            "title": escape_html(name, quote=True),
            "depth": depths[name],
            "InDegree": incoming[name],
            "OutDegree": outgoing[name],
            "Degree": incoming[name] + outgoing[name],
        } for name in graph.nodes
    ])
    edges = pd.DataFrame([
        {"from": parent, "to": child, "strength": "medium"}
        for parent, child in graph.edges
    ], columns=["from", "to", "strength"])
    return edges, nodes


def _search_english_id(graph_data, search_text):
    needle = (search_text or "").casefold()
    for node in graph_data["nodes"]:
        node["hidden"] = needle not in str(node["id"]).casefold()
    return graph_data


def _descendants(component):
    pending = [component]
    while pending:
        item = pending.pop()
        yield item
        children = getattr(item, "children", None)
        if isinstance(children, (list, tuple)):
            pending.extend(children)
        elif children is not None and not isinstance(children, (str, int, float)):
            pending.append(children)


def _normalize_upstream_layout(layout):
    """Restrict Jaal's huge logo and Bootstrap negative outer row margins."""
    from dash import html
    import dash_bootstrap_components as dbc

    for item in _descendants(layout):
        if isinstance(item, html.Img) and isinstance(
            getattr(item, "src", None), str
        ) and item.src.startswith("data:image/png;base64,"):
            if item.width == "80px":
                item.width = 80
                item.style = {**(getattr(item, "style", None) or {}),
                              "width": "80px", "maxWidth": "100%",
                              "height": "auto"}
                break
    if isinstance(layout, html.Div):
        children = layout.children
        if isinstance(children, (list, tuple)):
            for row in children:
                if isinstance(row, dbc.Row):
                    classes = (getattr(row, "className", None) or "").split()
                    if "g-0" not in classes:
                        row.className = " ".join([*classes, "g-0"])


def build_app(graph: Graph, *, root=None, requests_pathname_prefix="/"):
    """Build an independent localhost-ready Dash Jaal app, with all four modes.

    The original Jaal Search/Filter/Color/Size callbacks are preserved.
    JavaScript is installed from THIS package, not from the calling project.
    """
    from .data import GraphInputError
    from .modes import layout_options
    from . import ASSETS_DIR

    prefix = requests_pathname_prefix
    if (not isinstance(prefix, str) or
            not prefix.startswith("/") or not prefix.endswith("/") or
            "//" in prefix):
        raise GraphInputError(
            "requests_pathname_prefix must be an absolute slash-terminated path"
        )
    if not graph.edges:
        raise GraphInputError(
            "Jaal requires at least one visible directed edge; "
            "select a parent/ancestor rather than an isolated leaf"
        )
    if len(graph.nodes) > 3000 or len(graph.edges) > 5000:
        raise GraphInputError(
            "Graph must be bounded before Jaal app construction"
        )

    from dash import (
        Dash, Input, Output, ClientsideFunction, callback_context,
        dcc, html, no_update,
    )
    from jaal import Jaal

    edges, nodes = to_jaal_dataframes(graph, root=root)
    network = Jaal(edges, nodes)
    network._callback_search_graph = _search_english_id
    for collection in (network.data, network.filtered_data):
        for node in collection["nodes"]:
            if node.get("shape") == "dot":
                del node["shape"]
            # visdcc's Popup.setText uses innerHTML for string title values.
            # Escape title, never IDs/labels (canvas labels are plain text).
            # Jaal.parse_dataframe may recompute title after the CSV adapter.
            node["title"] = escape_html(str(node["id"]), quote=True)
        # Jaal's from+"__"+to edge ID collides for arbitrary string IDs.
        for index, edge in enumerate(collection["edges"]):
            edge["id"] = f"jaal-edge-{index}"
            if isinstance(edge.get("title"), str):
                edge["title"] = escape_html(edge["title"], quote=True)

    original_app = network.create(directed=True, vis_opts={
        "height": "600px",
        "interaction": {"hover": True},
        "physics": {"enabled": True, "stabilization": {"iterations": 100}},
    })
    graph_network = next(
        (item for item in _descendants(original_app.layout)
         if getattr(item, "id", None) == "graph"), None
    )
    if graph_network is None or not isinstance(graph_network.options, dict):
        raise RuntimeError("Original Jaal graph/options layout contract changed")
    base = deepcopy(graph_network.options)
    base.setdefault("nodes", {}).setdefault("shape", "dot")
    graph_network.options = deepcopy(base)
    _normalize_upstream_layout(original_app.layout)

    controls = html.Div([
        html.Span("顯示模式："),
        dcc.RadioItems(
            id="jaal-original-layout-mode",
            options=[
                {"label": "網狀（全展開）", "value": "network"},
                {"label": "網狀（收攏）", "value": "network-collapsed"},
                {"label": "階層（全展開）", "value": "hierarchical"},
                {"label": "階層（收攏）", "value": "hierarchical-collapsed"},
            ],
            value="network", inline=True,
        ),
        dcc.Checklist(
            id="jaal-original-chinese-labels",
            options=[{"label": "優先顯示中文名稱（無翻譯時顯示英文）",
                      "value": "zh"}],
            value=[], inline=True,
        ),
        dcc.Store(id="jaal-original-ct-translations",
                  data=graph.translations, storage_type="memory"),
        dcc.Interval(id="jaal-original-physics-restore",
                     interval=300, disabled=True, n_intervals=0),
        html.Span("收攏模式：點擊節點展開／收合一層；數字為不同子孫數。",
                  style={"fontSize": "12px", "color": "#475569"}),
    ], style={"display": "flex", "alignItems": "center", "gap": "12px",
              "flexWrap": "wrap", "padding": "8px 4px",
              "position": "sticky", "top": "0",
              "backgroundColor": "rgba(255,255,255,0.93)", "zIndex": 20})

    # Jaal creates a Dash instance without a configurable asset directory.
    # Construct a correctly configured shell and reuse its actual callbacks,
    # rather than using a separate graph implementation or copying JS from
    # the old application at runtime. The shell serves bundled assets offline.
    app = Dash(
        __name__, assets_folder=str(ASSETS_DIR),
        requests_pathname_prefix=prefix,
        routes_pathname_prefix="/",
        # Original Jaal uses CDN-only Bootstrap; include a locally served
        # MIT-licensed copy so controls retain layout even on an air-gapped PC.
        external_stylesheets=[
            prefix + "assets/bootstrap.min.css",
            *list(original_app.config.external_stylesheets),
        ],
    )
    app.layout = html.Div([controls, original_app.layout])
    app.callback_map.update(original_app.callback_map)
    app._callback_list.extend(original_app._callback_list)
    if not app.callback_map or len(app.callback_map) != len(original_app.callback_map):
        raise RuntimeError("Original Jaal callbacks were not preserved")

    @app.callback(
        Output("graph", "options"),
        Output("jaal-original-physics-restore", "disabled"),
        Input("jaal-original-layout-mode", "value"),
        Input("jaal-original-physics-restore", "n_intervals"),
        prevent_initial_call=True,
    )
    def switch_mode(mode, _ticks):
        triggered = callback_context.triggered[0]["prop_id"].split(".", 1)[0]
        if triggered == "jaal-original-physics-restore":
            if mode not in ("network", "network-collapsed"):
                return no_update, True
            reset = layout_options(base, mode)
            physics = base.get("physics", {})
            enabled = physics.get("enabled", True) if isinstance(
                physics, dict
            ) else bool(physics)
            return {
                "physics": {"enabled": enabled},
                "edges": {"smooth": reset["edges"]["smooth"]},
                "nodes": {key: reset["nodes"][key] for key in (
                    "shape", "widthConstraint", "margin", "borderWidth"
                )},
            }, True
        if mode in (
            "network", "network-collapsed",
            "hierarchical", "hierarchical-collapsed",
        ):
            return layout_options(base, mode), mode.startswith("hierarchical")
        raise ValueError("Unsupported Jaal layout mode")

    app.clientside_callback(
        ClientsideFunction(namespace="jaal_visible_labels",
                           function_name="apply"),
        Output("graph", "run"),
        Input("jaal-original-layout-mode", "value"),
        Input("graph", "data"),
        Input("jaal-original-chinese-labels", "value"),
        Input("jaal-original-ct-translations", "data"),
    )
    return app
