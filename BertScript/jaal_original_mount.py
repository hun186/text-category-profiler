"""Mount the *original* Jaal Dash application under the Stage 4 port.

Jaal retains its own layout, visdcc graph, search/filter/color/size callbacks.
There is no second listening socket. Instances are constructed only when the
user explicitly clicks Load, and only for a bounded taxonomy subtree.
"""
from __future__ import annotations

from collections import OrderedDict, deque
import csv
import hashlib
import logging
import os
import json
import importlib.metadata
from copy import deepcopy
from pathlib import Path
from threading import RLock

from werkzeug.middleware.dispatcher import DispatcherMiddleware

from ClassesTree.Visualization.embedded_tree import load_graph
from ClassesTree.Visualization.jaal.label_format import enable_embedded_jaal_global_node_shapes


MOUNT_PATH = "/jaal-original"
DEFAULT_ROOT = "TW Affairs"
ORDINARY_NODE_LIMIT = 250
HEAVY_NODE_LIMIT = 3000
HEAVY_EDGE_LIMIT = 5000
MAX_LIVE_GRAPHS = 3

LOGGER = logging.getLogger(__name__)

# Bundled with Stage 4; the original Jaal stylesheet is CDN-hosted, which
# cannot be the only styling source for an iframe in an offline deployment.
STAGE4_ASSETS = Path(__file__).resolve().parent / "assets"
# Import standalone assets lazily: dependency-light ClassTable commands and
# Stage 4's unloaded panel must not import Jaal until the user loads it.
# The installed package is pinned to an audited GitHub commit in requirements.txt.
def _portable_jaal_assets_dir():
    from jaal_topology import ASSETS_DIR
    return ASSETS_DIR
PORTABLE_JS_FILES = ("16.jaal_visible_labels.js", "17.jaal_structural_collapse.js")
CANDIDATE_SHA = "3e9355851357326ac0e47848b8cef64b50bf1b83"
CANDIDATE_ENV = "JAAL_STAGE4_COMMUNITY_CANDIDATE"
CANDIDATE_JS_FILES = PORTABLE_JS_FILES + ("18.jaal_community_collapse.js",)
LOCAL_BOOTSTRAP = "bootstrap@5.3.1/bootstrap.min.css"


def subtree_stats(root):
    """Count descendants and induced edges with no Jaal app construction."""
    edges, nodes, adjacency = load_graph()
    if not isinstance(root, str) or not root.strip() or root.strip() not in nodes:
        raise ValueError("請輸入 TopicTree 中存在的英文 ClassLabel。")
    root = root.strip()
    selected = {root}
    pending = deque([root])
    while pending:
        for child in adjacency.get(pending.popleft(), ()):
            if child not in selected:
                selected.add(child)
                pending.append(child)
    edge_count = sum(1 for src, dst in edges
                     if src in selected and dst in selected)
    return {"nodes": len(selected), "edges": edge_count, "root": root}



def _community_candidate_enabled():
    """Fail closed unless the opt-in exact upstream candidate is installed."""
    value = os.environ.get(CANDIDATE_ENV, "0")
    if value in ("", "0"):
        return False
    if value != "1":
        raise ValueError(f"{CANDIDATE_ENV} only accepts 0 or 1")
    dist = importlib.metadata.distribution("jaal-topology-viewer")
    info = json.loads(dist.read_text("direct_url.json") or "{}")
    if info.get("vcs_info", {}).get("commit_id") != CANDIDATE_SHA:
        raise RuntimeError(
            "Stage 4 experimental Louvain requires isolated Jaal candidate "
            f"exact SHA {CANDIDATE_SHA}; production pin stays unchanged"
        )
    return True


def _community_candidate_context(layout):
    """Partition only loaded Jaal source IDs; never change underlying graph."""
    from jaal_topology.data import Graph, assess_structural_collapse
    from jaal_topology.community import detect_louvain

    pending = [layout]
    found = []
    while pending:
        item = pending.pop()
        if getattr(item, "id", None) == "graph":
            found.append(item)
        children = getattr(item, "children", None)
        if isinstance(children, (list, tuple)):
            pending.extend(children)
        elif children is not None and not isinstance(children, (str, int, float)):
            pending.append(children)
    if len(found) != 1:
        raise RuntimeError("Expected one original Jaal visdcc graph")
    source = found[0].data
    if not isinstance(source, dict):
        raise RuntimeError("Original Jaal graph data contract changed")
    ids = tuple(str(node["id"]) for node in source["nodes"])
    if len(ids) != len(set(ids)):
        raise RuntimeError("Original Jaal IDs must be unique")
    # Duplicate topic pairs may exist; Louvain requires unique directed pairs.
    # Do not alter the visdcc network's original nodes or edge records.
    edges = tuple(dict.fromkeys(
        (str(row["from"]), str(row["to"])) for row in source["edges"]
    ))
    graph = Graph(edges, ids)
    profile = assess_structural_collapse(graph)
    groups = detect_louvain(graph).member_to_group
    return {"eligible": not profile.has_cycle,
            "kind": profile.graph_kind,
            "multi_parent": profile.multi_parent_nodes,
            "membership": groups}


def _normalize_original_jaal_logo(layout):
    """Constrain Jaal's inline logo without replacing its layout/controls.

    Upstream Jaal uses html.Img(width="80px"); the HTML width attribute
    expects an integer and can be ignored, exposing the large source bitmap.
    Scope this patch to that exact inline PNG logo in the embedded app.
    """
    from dash import html

    pending = [layout]
    while pending:
        item = pending.pop()
        if (isinstance(item, html.Img)
                and isinstance(getattr(item, "src", None), str)
                and item.src.startswith("data:image/png;base64,")
                and getattr(item, "width", None) == "80px"):
            item.width = 80
            item.style = {
                **(getattr(item, "style", None) or {}),
                "width": "80px",
                "height": "auto",
                "maxWidth": "100%",
            }
            return True
        children = getattr(item, "children", None)
        if isinstance(children, (list, tuple)):
            pending.extend(children)
        elif children is not None and not isinstance(children, (str, int, float)):
            pending.append(children)
    return False


def _remove_embedded_jaal_outer_row_gutters(layout):
    """Keep Jaal's two outer Bootstrap rows inside the iframe viewport.

    Bootstrap .row has negative left/right margins to counter child column
    padding. Those margins are valid inside a .container, but upstream Jaal
    renders its root rows directly in a Div. The narrow overflow can create
    both horizontal and vertical iframe scrollbars. Apply Bootstrap's g-0
    *only* to the two root rows; never hide overflow or clip labels/controls.
    """
    import dash_bootstrap_components as dbc
    from dash import html

    if not isinstance(layout, html.Div):
        raise RuntimeError("Original Jaal outer layout is no longer a Div")
    outer_rows = getattr(layout, "children", None)
    if (not isinstance(outer_rows, (tuple, list))
            or len(outer_rows) != 2
            or not all(isinstance(row, dbc.Row) for row in outer_rows)):
        raise RuntimeError("Original Jaal outer row structure changed")
    for row in outer_rows:
        classes = (row.className or "").split()
        if "g-0" not in classes:
            row.className = " ".join([*classes, "g-0"])


from functools import lru_cache


@lru_cache(maxsize=1)
def _portable_jaal_layout_provider():
    """Import four-mode options from the pinned standalone distribution."""
    from jaal_topology.modes import layout_options
    return layout_options


def _jaal_layout_options(base_options, mode):
    """Use the reusable package's authoritative four-mode layout options."""
    return _portable_jaal_layout_provider()(base_options, mode)


def _register_embedded_jaal_layout_mode(app, base_options, candidate=None):
    """Switch layout, then restore network physics after vis.js unwinds hierarchy.

    vis-network LayoutEngine.setOptions() restores an internal physics backup
    *after* applying options when hierarchical mode is disabled. A one-shot
    delayed second net.setOptions() is required to re-enable physics reliably.
    No new graph/data instance is created; the timer is idle otherwise.
    """
    from dash import Input, Output, callback_context, no_update

    @app.callback(
        Output("graph", "options"),
        Output("jaal-original-physics-restore", "disabled"),
        Input("jaal-original-layout-mode", "value"),
        Input("jaal-original-physics-restore", "n_intervals"),
        prevent_initial_call=True,
    )
    def choose_layout(mode, _ticks):
        if (candidate is not None and not candidate["eligible"]
                and mode in ("network-collapsed", "hierarchical-collapsed")):
            raise ValueError("Descendant collapse unavailable on directed cycles")
        triggered = callback_context.triggered[0]["prop_id"].split(".", 1)[0]
        if triggered == "jaal-original-physics-restore":
            # A quick switch back to hierarchy must never reactivate physics.
            if mode not in (("network", "network-collapsed", "network-community-collapsed")
                            if candidate is not None else ("network", "network-collapsed")):
                return no_update, True
            baseline = base_options.get("physics", {})
            enabled = baseline.get("enabled", True) if isinstance(
                baseline, dict
            ) else bool(baseline)
            # Exiting hierarchy also restores vis.js' saved edge.smooth
            # boolean, masking our first-phase smooth.type reset. Restore
            # both affected effective settings *after* that internal merge.
            reset = _jaal_layout_options(base_options, mode)
            return {
                "physics": {"enabled": enabled},
                "edges": {"smooth": reset["edges"]["smooth"]},
                "nodes": {
                    key: reset["nodes"][key]
                    for key in ("shape", "widthConstraint", "margin", "borderWidth")
                },
            }, True
        if mode in ("hierarchical", "hierarchical-collapsed"):
            return _jaal_layout_options(base_options, mode), True
        if mode in (("network", "network-collapsed", "network-community-collapsed")
                    if candidate is not None else ("network", "network-collapsed")):
            # Step 1: exit hierarchical layout, restoring original vis.js
            # settings. LayoutEngine can still override physics.enabled.
            # Step 2: timer tick restores enabled after the React update.
            return _jaal_layout_options(base_options, mode), False
        raise ValueError("Unsupported Jaal layout mode")


def _class_table_labels_for_nodes(node_ids, path=None):
    """Read only CT translations for the *loaded* graph; empty/missing -> English.

    Do not alter the authoritative graph, Jaal Search, or ClassTable.csv.
    A blank CT is a display fallback, not an identity or validation error.
    """
    from BertScript.class_table_metadata import DEFAULT_CSV, HEADERS
    selected = {str(node_id) for node_id in node_ids}
    translations = {}
    seen = set()
    with open(path or DEFAULT_CSV, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if tuple(reader.fieldnames or ()) != HEADERS:
            raise ValueError("ClassTable CSV must have ClassLabel,CT,Explanation,Notes columns")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed ClassTable CSV row")
            key = row["ClassLabel"]
            if key not in selected:
                continue
            if key in seen:
                raise ValueError(f"Duplicate ClassTable ClassLabel: {key!r}")
            seen.add(key)
            translated = row["CT"].strip()
            if translated:
                translations[key] = translated
    return translations


def _register_embedded_jaal_visible_labels(app, candidate=None):
    """Project label text onto visdcc's live vis.DataSet when Dash data changes.

    Dash's initial graph.data may contain explicit newlines yet the user's
    browser can still paint long one-line labels. visdcc's documented 'run'
    prop executes on Network.render, after a prop update. Keep this in a
    separate output from Jaal's seven original graph.data inputs.
    """
    from dash import Input, Output, ClientsideFunction

    app.clientside_callback(
        ClientsideFunction(
            namespace="jaal_visible_labels", function_name="apply"
        ),
        Output("graph", "run"),
        Input("jaal-original-layout-mode", "value"),
        Input("graph", "data"),
        Input("jaal-original-chinese-labels", "value"),
        Input("jaal-original-ct-translations", "data"),
        *([Input("jaal-community-membership", "data"),
           Input("jaal-structural-eligible", "data")] if candidate is not None else []),
        prevent_initial_call=False,
    )


def _add_embedded_jaal_sidebar_toggle(layout, candidate=None):
    """Add a toggle without rebuilding the original Jaal graph or controls.

    Only the Jaal-owned 3/9 Bootstrap columns are decorated. The button lives
    in the graph column so it remains reachable when the sidebar is hidden.
    """
    import dash_bootstrap_components as dbc
    from dash import dcc, html

    def descendants(component):
        pending = [component]
        while pending:
            item = pending.pop()
            yield item
            children = getattr(item, "children", None)
            if isinstance(children, (list, tuple)):
                pending.extend(reversed(children))
            elif children is not None and not isinstance(children, (str, int, float)):
                pending.append(children)

    def contains_id(component, component_id):
        return any(getattr(item, "id", None) == component_id
                   for item in descendants(component))

    matches = []
    for item in descendants(layout):
        if not isinstance(item, dbc.Row):
            continue
        columns = getattr(item, "children", None)
        if not isinstance(columns, (tuple, list)) or len(columns) != 2:
            continue
        left, right = columns
        if (isinstance(left, dbc.Col) and isinstance(right, dbc.Col)
                and contains_id(left, "search_graph")
                and contains_id(right, "graph")):
            matches.append((left, right))
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one original Jaal settings/graph row")
    sidebar, graph = matches[0]
    if sidebar.width != 3 or graph.width != 9:
        raise RuntimeError("Original Jaal sidebar column sizes changed")
    sidebar.id = "jaal-original-settings-column"
    # Upstream Jaal centers the settings card vertically within the graph row
    # ("align-items": "center"). When Filter/Color are collapsed the card is
    # shorter than the 600px network, leaving a large blank strip above it.
    # Adjust only the embedded original Jaal column, preserving all controls.
    sidebar.style = {
        **(sidebar.style or {}),
        "align-items": "flex-start",
    }
    graph.id = "jaal-original-graph-column"
    # Make a defensive snapshot before any user-driven options callback.
    # graph.children is Jaal's existing visdcc.Network, not a replacement.
    network = graph.children
    if (getattr(network, "id", None) != "graph"
            or not isinstance(getattr(network, "options", None), dict)):
        raise RuntimeError("Original Jaal network/options contract changed")
    base_options = deepcopy(network.options)
    # Jaal instance graph.data has been adapted to omit explicit node
    # shapes. Keep the original network in dot mode until hierarchy selected.
    base_options.setdefault("nodes", {}).setdefault("shape", "dot")
    network.options = deepcopy(base_options)
    toggle = html.Button(
        "◀ 收合左側設定", id="jaal-original-sidebar-toggle", n_clicks=0,
        className="btn btn-outline-secondary btn-sm",
        title="隱藏左側設定，讓分類圖展開",
        **{"aria-label": "收合或展開 Jaal 左側設定面板"},
    )
    # Read the revision from the imported Python module, never Git Desktop's
    # checked-out HEAD: an old server process must keep showing its OLD badge.
    from ClassesTree.Visualization.jaal.label_format import LABEL_RENDERER_REVISION

    # Only the already-loaded subgraph's IDs are sent to the browser.
    # Empty ClassTable CT values or absent rows fall back to English at render.
    translations = _class_table_labels_for_nodes(
        (node["id"] for node in network.data["nodes"])
    )
    chinese_choice = dcc.Checklist(
        id="jaal-original-chinese-labels",
        options=[{"label": "優先顯示中文名稱（無翻譯時顯示英文）", "value": "zh"}],
        value=[],
        inline=True,
        inputStyle={"marginRight": "5px"},
        labelStyle={"cursor": "pointer"},
    )
    translation_store = dcc.Store(
        id="jaal-original-ct-translations",
        data=translations,
        storage_type="memory",
    )
    mode_options = [
        {"label": "網狀（全展開）", "value": "network"},
        {"label": "網狀（收攏）", "value": "network-collapsed"},
        {"label": "階層（全展開）", "value": "hierarchical"},
        {"label": "階層（收攏）", "value": "hierarchical-collapsed"},
    ]
    if candidate is not None:
        mode_options.insert(2, {"label": "網狀（社群收攏・Louvain）",
                                "value": "network-community-collapsed"})
        for choice in mode_options:
            if choice["value"] in ("network-collapsed", "hierarchical-collapsed"):
                choice["disabled"] = not candidate["eligible"]
    mode_choice = dcc.RadioItems(
        id="jaal-original-layout-mode",
        options=mode_options,
        value="network",
        inline=True,
        labelStyle={"marginRight": "12px", "cursor": "pointer"},
        inputStyle={"marginRight": "4px"},
    )
    toolbar = html.Div(
        [toggle, html.Span("顯示模式："), mode_choice, chinese_choice,
         translation_store,
         *([
             dcc.Store(id="jaal-community-membership",
                       data=candidate["membership"], storage_type="memory"),
             dcc.Store(id="jaal-structural-eligible",
                       data=candidate["eligible"], storage_type="memory"),
             html.Span(
                 "圖形類型：" + {
                     "tree": "樹狀階層（單一起點）",
                     "forest": "樹狀森林（多個起點）",
                     "dag": "無環 DAG（多父節點）",
                     "cyclic": "一般有環網路（不適合子樹收攏）",
                 }[candidate["kind"]],
                 id="jaal-original-graph-profile",
                 style={"fontSize": "12px", "fontWeight": 600}),
         ] if candidate is not None else []),
         html.Span("標籤版本：" + LABEL_RENDERER_REVISION,
                   id="jaal-original-label-revision",
                   title="這是當前 Python 服務實際載入的標籤版本；"
                         "若更新 Git 後仍看不到此版本，請完全停止 8059 服務再重新啟動",
                   style={"fontSize": "12px", "color": "#475569"}),
         html.Span(
                   ("偵測到有向迴路：停用兩種子樹收攏；可使用網狀（社群收攏・Louvain）。"
                    if candidate is not None and not candidate["eligible"] else
                    "無環 DAG 可能包含共享後代；數字代表可達節點，不一定是獨占下屬。"
                    if candidate is not None and candidate["multi_parent"] else
                    "收攏模式：節點下方數字＝不同子孫節點數；點擊展開／收合一層。"
                    " 原本全展開模式保留。")
                   + (" 社群分群不代表職級。" if candidate is not None else ""),
                   id="jaal-original-hierarchy-hint",
                   style={"fontSize": "12px", "color": "#475569"}),
         dcc.Interval(id="jaal-original-physics-restore",
                      interval=300, disabled=True, n_intervals=0)],
        style={
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "flex-start",
            "gap": "12px",
            "flexWrap": "wrap",
            "padding": "6px 4px",
            "position": "sticky",
            "top": "0",
            "zIndex": 20,
            "backgroundColor": "rgba(255,255,255,0.93)",
        },
    )
    graph.children = [toolbar, graph.children]
    return base_options


def _sidebar_toggle_geometry(clicks):
    """Pure view geometry: no graph data, settings or server instances reset."""
    collapsed = bool(clicks and clicks % 2)
    sidebar_style = {"display": "none"} if collapsed else {
        "display": "flex",
        "justifyContent": "center",
        "alignItems": "flex-start",
    }
    return (
        sidebar_style,
        12 if collapsed else 9,
        "▶ 展開左側設定" if collapsed else "◀ 收合左側設定",
    )


def _register_embedded_jaal_sidebar_toggle(app):
    from dash import Input, Output

    @app.callback(
        Output("jaal-original-settings-column", "style"),
        Output("jaal-original-graph-column", "width"),
        Output("jaal-original-sidebar-toggle", "children"),
        Input("jaal-original-sidebar-toggle", "n_clicks"),
        prevent_initial_call=True,
    )
    def toggle_sidebar(clicks):
        return _sidebar_toggle_geometry(clicks)

    # vis.js may listen for a window resize rather than a parent width change.
    # Send only a resize notification after React applies the new Bootstrap
    # column width. Never reconstruct the graph or call vis-network.fit().
    app.clientside_callback(
        """
        function(width) {
            window.requestAnimationFrame(function() {
                window.requestAnimationFrame(function() {
                    window.dispatchEvent(new Event("resize"));
                });
            });
            return width === 12
                ? "展開左側 Search / Filter / Color / Size 設定"
                : "收合左側 Search / Filter / Color / Size 設定";
        }
        """,
        Output("jaal-original-sidebar-toggle", "title"),
        Input("jaal-original-graph-column", "width"),
    )


def prefix_original_jaal(original_app, prefix):
    """Preserve Jaal's actual layout/callbacks in a correctly prefixed Dash.

    Jaal.create() constructs Dash without a path argument; modern Dash marks
    the prefix read-only. A new Dash instance supplies the path *at creation*,
    then reuses Jaal's registered callback objects and complete UI unchanged.
    This small adapter uses Dash callback registry internals, so the Hosted
    real-Jaal WSGI smoke test guards future Dash library updates.
    """
    from dash import Dash

    if not prefix.startswith("/") or not prefix.endswith("/"):
        raise ValueError("Jaal mount prefix must be an absolute slash path")
    if not (STAGE4_ASSETS / LOCAL_BOOTSTRAP).is_file():
        raise RuntimeError("Stage 4 bundled Bootstrap stylesheet is missing")
    candidate_enabled = _community_candidate_enabled()
    candidate = (_community_candidate_context(original_app.layout)
                 if candidate_enabled else None)
    javascript_files = (CANDIDATE_JS_FILES if candidate_enabled
                        else PORTABLE_JS_FILES)
    child_app = Dash(
        __name__,
        requests_pathname_prefix=prefix,
        routes_pathname_prefix="/",
        assets_folder=str(STAGE4_ASSETS),
        # Browser runtimes are served from the reusable standalone package,
        # not duplicate copies under BertScript/assets.
        external_scripts=[
            prefix + "assets/" + name for name in javascript_files
        ],
        # Keep upstream styles, but serve the required Bootstrap grid from
        # this same-origin submount. The original CDN can be unavailable.
        external_stylesheets=[
            prefix + "assets/" + LOCAL_BOOTSTRAP,
            *list(original_app.config.external_stylesheets),
        ],
    )
    # Serve exact static runtime filenames through the same-origin child
    # Flask app. Dash also owns the generic /assets/<path> route; explicit
    # paths take precedence and let the old browser URL contract survive.
    from flask import send_from_directory
    portable_assets = _portable_jaal_assets_dir()
    for asset_name in javascript_files:
        if not (portable_assets / asset_name).is_file():
            raise RuntimeError(f"Bundled portable Jaal asset missing: {asset_name}")

        def serve_portable_asset(asset=asset_name):
            return send_from_directory(
                str(portable_assets), asset,
                mimetype="application/javascript",
            )
        child_app.server.add_url_rule(
            "/assets/" + asset_name,
            endpoint="portable_jaal_" + asset_name.replace(".", "_"),
            view_func=serve_portable_asset,
        )
    _normalize_original_jaal_logo(original_app.layout)
    _remove_embedded_jaal_outer_row_gutters(original_app.layout)
    base_options = _add_embedded_jaal_sidebar_toggle(original_app.layout, candidate)
    # A stable content boundary lets the *child* iframe measure actual
    # rendered height (logo + controls + graph), independent of the original
    # visdcc graph's 600px canvas and the parent's initial fallback height.
    # Keep the original Jaal layout and callbacks nested, not recreated.
    from dash import html
    child_app.layout = html.Div(
        original_app.layout, id="jaal-original-content"
    )
    child_app.callback_map.update(original_app.callback_map)
    child_app._callback_list.extend(original_app._callback_list)
    if not child_app.callback_map or len(child_app.callback_map) != len(original_app.callback_map):
        raise RuntimeError("Original Jaal callbacks could not be preserved")
    _register_embedded_jaal_sidebar_toggle(child_app)
    _register_embedded_jaal_layout_mode(child_app, base_options, candidate)
    _register_embedded_jaal_visible_labels(child_app, candidate)
    return child_app


def _make_original_jaal(root, prefix):
    """Re-use exact historic Jaal data pipeline, layout, and UI callbacks."""
    from BertScript.jaal_runtime_diagnostics import check_dash_visdcc_compatibility
    check_dash_visdcc_compatibility()
    from ClassesTree.Visualization.jaal.jaalViewer import JaalViewMain

    original_app = JaalViewMain(QueryRoot=root, createMode=True)
    return prefix_original_jaal(original_app, prefix)


def _response(start_response, status, message):
    data = message.encode("utf-8")
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"),
                            ("Content-Length", str(len(data))),
                            ("Cache-Control", "no-store")])
    return [data]


class OriginalJaalRouter:
    """WSGI adapter for a few explicitly loaded and immutable Jaal sub-apps."""

    def __init__(self, build_app=None):
        self._lock = RLock()
        self._roots = OrderedDict()
        self._apps = {}
        self._build_app = build_app or _make_original_jaal

    def mount(self, flask_server):
        """Install the same-origin, same-port submount before server start."""
        with self._lock:
            installed = getattr(flask_server, "_original_jaal_router", None)
            if installed is self:
                return
            if installed is not None:
                raise RuntimeError("An original Jaal router is already mounted")
            flask_server.wsgi_app = DispatcherMiddleware(
                flask_server.wsgi_app, {MOUNT_PATH: self}
            )
            flask_server._original_jaal_router = self

    def prepare(self, root=DEFAULT_ROOT, *, confirmed_large=False):
        """No heavy Jaal calculation; register only after explicit user click."""
        stats = subtree_stats(root)
        if stats["nodes"] < 2:
            raise ValueError("此類別沒有可繪製的子樹關係；請選其他根類別。")
        if stats["nodes"] > HEAVY_NODE_LIMIT or stats["edges"] > HEAVY_EDGE_LIMIT:
            raise ValueError("超過原版 Jaal 安全上限，請縮小根類別範圍。")
        if stats["nodes"] > ORDINARY_NODE_LIMIT and not confirmed_large:
            raise ValueError(
                f"這個子樹有 {stats['nodes']:,} 個節點、{stats['edges']:,} 條關係；"
                "請先勾選大型圖形確認，再按載入。"
            )
        key = hashlib.sha256(stats["root"].encode("utf-8")).hexdigest()[:24]
        with self._lock:
            if key not in self._roots:
                if len(self._roots) >= MAX_LIVE_GRAPHS:
                    raise ValueError(
                        "原版 Jaal 已保留多個檢視範圍；為控制記憶體，"
                        "目前不再建立其他圖形。請重新啟動 Stage 4 以清空。"
                    )
                self._roots[key] = stats["root"]
        return f"{MOUNT_PATH}/{key}/", stats

    def __call__(self, environ, start_response):
        """Called on iframe HTTP requests; never on the main page request."""
        path = environ.get("PATH_INFO", "")
        key = path.strip("/").split("/", 1)[0]
        with self._lock:
            root = self._roots.get(key)
            if root is None:
                return _response(start_response, "404 Not Found",
                                 "此 Jaal 檢視範圍尚未由主站啟用。")
            if key not in self._apps:
                try:
                    prefix = f"{MOUNT_PATH}/{key}/"
                    self._apps[key] = self._build_app(root, prefix)
                except Exception as exc:
                    # Keep the main Dash server alive. The public iframe
                    # remains deliberately generic, but the local server
                    # console must include the actual missing attribute,
                    # traceback and failure stage for cross-machine diagnosis.
                    # Do not expose paths, environment values or tracebacks
                    # to the browser; do not automatically retry writes.
                    LOGGER.exception(
                        "Jaal lazy initialization failed for root %r "
                        "(subapp %s); inspect traceback above and run "
                        "python -m BertScript.jaal_runtime_diagnostics "
                        "--root %r in the SAME Python environment",
                        root, key, root,
                    )
                    return _response(
                        start_response, "503 Service Unavailable",
                        "原版 Jaal 載入失敗："
                        + type(exc).__name__
                        + "。請檢查 Stage 4 終端機紀錄、jaal/visdcc 安裝和資料。"
                    )
            child_app = self._apps[key]
        # Werkzeug 3 no longer exports pop_path_info. Split exactly the
        # registered hash segment; preserve SCRIPT_NAME for the sub-mounted
        # Dash application without touching the parent WSGI environment.
        prefix = "/" + key
        if path != prefix and not path.startswith(prefix + "/"):
            return _response(start_response, "404 Not Found", "路徑無效。")
        child_environ = environ.copy()
        child_environ["SCRIPT_NAME"] = (
            environ.get("SCRIPT_NAME", "") + prefix
        )
        child_environ["PATH_INFO"] = path[len(prefix):] or "/"
        return child_app.server.wsgi_app(child_environ, start_response)
