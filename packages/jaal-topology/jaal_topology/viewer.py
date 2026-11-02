"""Standalone Jaal rendering; independent of Stage 4 and taxonomy utilities.

Uses Jaal's real Search/Filter/Color/Size Dash app. Enriches the graph
with optional display-language and network/hierarchy controls. The full
Stage-4-only collapse animation remains a separate migration milestone.
"""
from __future__ import annotations

from copy import deepcopy
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
            "title": name,
            "depth": depths[name],
            "InDegree": incoming[name],
            "OutDegree": outgoing[name],
            "Degree": incoming[name] + outgoing[name],
        } for name in graph.nodes
    ])
    edges = pd.DataFrame([
        {"from": parent, "to": child, "strength": "medium"}
        for parent, child in graph.edges
    ])
    return edges, nodes


def _search_english_id(graph_data, search_text):
    needle = (search_text or "").casefold()
    for node in graph_data["nodes"]:
        node["hidden"] = needle not in str(node["id"]).casefold()
    return graph_data


def _mode_options(base, mode):
    options = deepcopy(base)
    if mode == "hierarchical":
        options.setdefault("layout", {})["hierarchical"] = {
            "enabled": True, "direction": "UD", "sortMethod": "directed",
            "levelSeparation": 260, "nodeSpacing": 285, "treeSpacing": 370,
            "blockShifting": True, "edgeMinimization": True,
            "parentCentralization": True,
        }
        options.setdefault("nodes", {}).update({
            "shape": "box", "widthConstraint": {"maximum": 178},
            "margin": 12, "borderWidth": 1,
        })
        options["physics"] = {"enabled": False}
        options.setdefault("edges", {})["smooth"] = {
            "enabled": True, "type": "cubicBezier",
            "forceDirection": "vertical", "roundness": 0.28,
        }
    elif mode == "network":
        options.setdefault("layout", {})["hierarchical"] = {"enabled": False}
        options.setdefault("nodes", {}).update({
            "shape": "dot", "widthConstraint": False,
            "margin": 0, "borderWidth": 1,
        })
        options["physics"] = deepcopy(base.get("physics", {"enabled": True}))
        options["physics"]["enabled"] = True
        options.setdefault("edges", {})["smooth"] = {
            "enabled": True, "type": "dynamic",
            "forceDirection": "none", "roundness": 0.5,
        }
    else:
        raise ValueError("mode must be network or hierarchical")
    return options


def build_app(graph: Graph, *, root=None):
    """Construct a real Jaal Dash server without starting a socket.

    Caller can use app.server as WSGI or app.run on localhost. The graphs
    must already have passed the bounded select_subgraph() safety gate.
    """
    from dash import dcc, html, Input, Output, State, callback_context, no_update
    from jaal import Jaal

    edges, nodes = to_jaal_dataframes(graph, root=root)
    network = Jaal(edges, nodes)
    network._callback_search_graph = _search_english_id
    # Jaal.parse_dataframe forces dot per node. Remove that *only* so
    # the network global node.shape can switch to boxes in hierarchy mode.
    for collection in (network.data, network.filtered_data):
        for node in collection["nodes"]:
            if node.get("shape") == "dot":
                del node["shape"]
    app = network.create(directed=True, vis_opts={
        "height": "600px",
        "interaction": {"hover": True},
        "physics": {"enabled": True, "stabilization": {"iterations": 100}},
    })
    # Inspect the real component rather than reconstructing Jaal controls.
    def all_children(component):
        stack = [component]
        while stack:
            item = stack.pop()
            yield item
            children = getattr(item, "children", None)
            if isinstance(children, (list, tuple)):
                stack.extend(children)
            elif children is not None and not isinstance(
                children, (str, int, float)
            ):
                stack.append(children)

    graph_network = next(
        (item for item in all_children(app.layout)
         if getattr(item, "id", None) == "graph"), None
    )
    if graph_network is None or not isinstance(graph_network.options, dict):
        raise RuntimeError("Jaal graph/options layout contract changed")
    base = deepcopy(graph_network.options)
    base.setdefault("nodes", {}).setdefault("shape", "dot")
    graph_network.options = deepcopy(base)

    controls = html.Div([
        html.Label("顯示模式：", htmlFor="topology-mode"),
        dcc.RadioItems(
            id="topology-mode",
            options=[{"label": "網狀", "value": "network"},
                     {"label": "階層", "value": "hierarchical"}],
            value="network", inline=True,
        ),
        dcc.Checklist(
            id="topology-chinese",
            options=[{"label": "優先顯示中文名稱（缺少翻譯顯示英文）",
                      "value": "zh"}],
            value=[], inline=True,
        ),
        dcc.Store(id="topology-translations", data=graph.translations),
        dcc.Interval(id="topology-physics-restore", interval=300,
                     disabled=True, n_intervals=0),
    ], style={"display": "flex", "alignItems": "center", "gap": "14px",
              "flexWrap": "wrap", "padding": "8px"})
    app.layout = html.Div([controls, app.layout])

    @app.callback(Output("graph", "options"),
                  Output("topology-physics-restore", "disabled"),
                  Input("topology-mode", "value"),
                  Input("topology-physics-restore", "n_intervals"),
                  prevent_initial_call=True)
    def switch_mode(mode, _ticks):
        triggered = callback_context.triggered[0]["prop_id"].split(".", 1)[0]
        if triggered == "topology-physics-restore":
            if mode != "network":
                return no_update, True
            return {
                "physics": {"enabled": True},
                "edges": {"smooth": _mode_options(base, "network")["edges"]["smooth"]},
                "nodes": _mode_options(base, "network")["nodes"],
            }, True
        return _mode_options(base, mode), mode == "hierarchical"

    # No interpolation of arbitrary CSV text into JS code. The labels only
    # enter the browser through the dcc.Store and are read as inert data.
    app.clientside_callback(
        """
        function(chinese, translations, graphData) {
            if (!graphData || !Array.isArray(graphData.nodes)) return "";
            var runtime = window.dash_clientside.topology_runtime =
                window.dash_clientside.topology_runtime || {};
            runtime.chinese = Array.isArray(chinese) && chinese.includes("zh");
            runtime.translations = translations || {};
            return "(function(){"
              + "var rt=window.dash_clientside.topology_runtime;"
              + "var ds=this.nn;if(!ds||!ds.get||!ds.update)return;"
              + "ds.update(ds.get().map(function(n){"
              + "var id=String(n.id);"
              + "var tr=Object.prototype.hasOwnProperty.call(rt.translations,id)"
              + "?rt.translations[id]:null;"
              + "var label=rt.chinese&&typeof tr==='string'&&tr.trim()"
              + "?tr.trim():id;"
              + "return {id:n.id,label:label,title:id};"
              + "}));"
              + "}).call(this);";
        }
        """,
        Output("graph", "run"),
        Input("topology-chinese", "value"),
        Input("topology-translations", "data"),
        Input("graph", "data"),
    )
    return app
