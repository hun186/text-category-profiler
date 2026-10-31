"""Mount the *original* Jaal Dash application under the Stage 4 port.

Jaal retains its own layout, visdcc graph, search/filter/color/size callbacks.
There is no second listening socket. Instances are constructed only when the
user explicitly clicks Load, and only for a bounded taxonomy subtree.
"""
from __future__ import annotations

from collections import OrderedDict, deque
import hashlib
from pathlib import Path
from threading import RLock

from werkzeug.middleware.dispatcher import DispatcherMiddleware

from ClassesTree.Visualization.embedded_tree import load_graph


MOUNT_PATH = "/jaal-original"
DEFAULT_ROOT = "TW Affairs"
ORDINARY_NODE_LIMIT = 250
HEAVY_NODE_LIMIT = 3000
HEAVY_EDGE_LIMIT = 5000
MAX_LIVE_GRAPHS = 3

# Bundled with Stage 4; the original Jaal stylesheet is CDN-hosted, which
# cannot be the only styling source for an iframe in an offline deployment.
STAGE4_ASSETS = Path(__file__).resolve().parent / "assets"
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
    child_app = Dash(
        __name__,
        requests_pathname_prefix=prefix,
        routes_pathname_prefix="/",
        assets_folder=str(STAGE4_ASSETS),
        # Keep upstream styles, but serve the required Bootstrap grid from
        # this same-origin submount. The original CDN can be unavailable.
        external_stylesheets=[
            prefix + "assets/" + LOCAL_BOOTSTRAP,
            *list(original_app.config.external_stylesheets),
        ],
    )
    _normalize_original_jaal_logo(original_app.layout)
    child_app.layout = original_app.layout
    child_app.callback_map.update(original_app.callback_map)
    child_app._callback_list.extend(original_app._callback_list)
    if not child_app.callback_map or len(child_app.callback_map) != len(original_app.callback_map):
        raise RuntimeError("Original Jaal callbacks could not be preserved")
    return child_app


def _make_original_jaal(root, prefix):
    """Re-use exact historic Jaal data pipeline, layout, and UI callbacks."""
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
                    # Keep the main Dash server alive if optional Jaal is
                    # missing or a subtree cannot be built.
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
