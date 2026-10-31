"""Same-port, lazy taxonomy viewer for the existing Stage 4 Dash application.

Jaal's standalone server is deliberately not imported or launched. The page
starts with zero graph elements; only explicit button events load taxonomy.
"""
from __future__ import annotations

import csv

from dash import Input, Output, State, ctx, dcc, html, no_update
import dash_bootstrap_components as dbc

try:
    import dash_cytoscape as cyto
except ImportError:
    cyto = None  # Keep the Stage 4 page visible with a clear install message.

from ClassesTree.Visualization.embedded_tree import (
    GraphLimitError, draw_graph,
)

GRAPH_STYLE = {"width": "100%", "height": "760px", "border": "1px solid #d7dce0"}
SUBGRAPH_LAYOUT = {"name": "breadthfirst", "directed": True, "animate": False,
                   "spacingFactor": 1.2}
FULL_LAYOUT = {"name": "grid", "animate": False}
BASE_STYLESHEET = [
    {"selector": "node", "style": {
        "label": "data(label)", "background-color": "#2374ab",
        "color": "#243746", "font-size": "11px",
        "text-wrap": "wrap", "text-max-width": "135px",
    }},
    {"selector": "edge", "style": {
        "curve-style": "bezier", "width": 1, "line-color": "#adb8c4",
        "target-arrow-shape": "triangle",
        "target-arrow-color": "#adb8c4", "arrow-scale": 0.7,
    }},
    {"selector": ".tree-root", "style": {
        "background-color": "#d77820", "font-weight": "bold",
    }},
    {"selector": ":selected", "style": {
        "background-color": "#ef6a56", "border-width": 2,
        "border-color": "#843b38",
    }},
]
# Rendering thousands of text labels is expensive. Full mode shows labels only
# when users select nodes (information also appears in the adjacent readout).
FULL_STYLESHEET = [
    dict(rule) for rule in BASE_STYLESHEET
]
FULL_STYLESHEET[0] = {
    "selector": "node", "style": {
        "background-color": "#2374ab", "width": 9, "height": 9,
    },
}


def build_tree_panel():
    """An always-visible Stage 4 card; only the graph contents are lazy.

    A missing optional Cytoscape package must not make the entire Stage 4
    application disappear or obscure the old Jaal Viewer entry point.
    """
    heading = dbc.CardHeader(
        html.H3("Classes Tree Jaal Viewer｜分類樹互動檢視器（內嵌版）")
    )
    if cyto is None:
        return dbc.Card([
            heading,
            dbc.CardBody([
                html.P("分類樹入口已載入，但尚未安裝 Dash Cytoscape，無法繪圖。"),
                html.Code("python -m pip install dash-cytoscape"),
                html.P("安裝完成後，請重新啟動 Stage 4 主網頁服務。"
                       "此版本不需要另外啟動 8053 port。"),
            ]),
        ], style={"width": "100%", "margin": "16px 0"})

    return dbc.Card([
        heading,
        dbc.CardBody([
            html.P("操作面板保持顯示；圖形預設不載入，也不會啟動第二個 port。"
                   "輸入英文 ClassLabel，再按「繪製子樹」。"
                   "要擴展範圍，先點圖上的節點，再按「展開所選節點」。"),
            html.Div([
                html.Label("類別名稱"),
                dcc.Input(id="JaalRoot", type="text", value="TW Affairs",
                          debounce=True, style={"width": "340px", "maxWidth": "95%"}),
                html.Label("子樹深度"),
                dcc.Dropdown(id="JaalDepth", value=2, clearable=False,
                             options=[{"label": str(n), "value": n}
                                      for n in range(1, 6)],
                             style={"width": "100px"}),
                html.Label("節點上限"),
                dcc.Dropdown(id="JaalMaxNodes", value=150, clearable=False,
                             options=[{"label": str(n), "value": n}
                                      for n in (50, 150, 300, 600, 1000)],
                             style={"width": "130px"}),
            ], style={"display": "flex", "gap": "12px", "alignItems": "center",
                      "flexWrap": "wrap"}),
            html.Div([
                html.Button("繪製子樹", id="btn_JaalViewer", n_clicks=0),
                html.Button("展開所選節點", id="btn_JaalViewerExpand", n_clicks=0),
                html.Button("清空畫布", id="btn_JaalViewerClear", n_clicks=0),
            ], style={"display": "flex", "gap": "12px", "margin": "12px 0",
                      "flexWrap": "wrap"}),
            html.Details([
                html.Summary("全圖模式（可能耗用較多瀏覽器資源）"),
                dcc.Checklist(
                    id="JaalAllowFull",
                    options=[{"label": "我了解全圖可能需要較多資源，並同意載入",
                              "value": "yes"}],
                    value=[],
                ),
                html.Button("確認繪製完整分類圖", id="btn_JaalViewerFull",
                            n_clicks=0),
                html.P("全圖僅在按下確認按鈕後載入，不套用力導向物理模擬，"
                       "並設有節點及邊數量硬限制。"),
            ], open=False),
            html.Div(id="JaalStatus", role="status",
                     children="尚未載入圖形；按「繪製子樹」後顯示。"),
            html.Div(id="JaalSelected", children="尚未選取節點。"),
            html.Details([
                html.Summary("展開／收合圖形"),
                cyto.Cytoscape(
                    id="JaalGraph", elements=[],
                    layout=SUBGRAPH_LAYOUT,
                    stylesheet=BASE_STYLESHEET,
                    style=GRAPH_STYLE,
                    minZoom=0.05, maxZoom=4,
                    wheelSensitivity=0.2,
                ),
            ], id="JaalViewerCardDetails", open=False),
        ]),
    ], style={"width": "100%", "margin": "16px 0"})


def render_action(action, *, root, depth, max_nodes, confirmed,
                  selected_node, previous_elements):
    """Pure callback decision policy; no work for denied/clear actions."""
    if action == "btn_JaalViewerClear":
        return [], SUBGRAPH_LAYOUT, BASE_STYLESHEET, "已清空畫布。", False
    if action == "btn_JaalViewerFull":
        if "yes" not in (confirmed or []):
            return no_update, no_update, no_update, "請先勾選全圖資源確認。", no_update
        report = draw_graph(full=True)
    elif action == "btn_JaalViewerExpand":
        node = (selected_node or {}).get("id")
        existing = [x["data"]["id"] for x in (previous_elements or [])
                    if "source" not in x.get("data", {})]
        if not node or node not in existing:
            return no_update, no_update, no_update, "請先在圖上點選一個節點。", no_update
        report = draw_graph(root=node, depth=depth, max_nodes=max_nodes,
                            existing_nodes=existing)
    elif action == "btn_JaalViewer":
        report = draw_graph(root=root, depth=depth, max_nodes=max_nodes)
    else:
        return no_update, no_update, no_update, no_update, no_update

    summary = (f"已顯示 {report['nodes']:,} 節點、{report['edges']:,} 關係"
               f"（整體 {report['total_nodes']:,} 節點／"
               f"{report['total_edges']:,} 關係）。")
    if report["truncated"]:
        summary += " 已達節點上限；可調高上限或更換根節點繼續探索。"
    return (report["elements"],
            FULL_LAYOUT if report["full"] else SUBGRAPH_LAYOUT,
            FULL_STYLESHEET if report["full"] else BASE_STYLESHEET,
            summary, True)


def register_tree_callbacks(app):
    if cyto is None:
        # No missing-output callbacks: show the install guidance instead.
        return

    @app.callback(
        Output("JaalGraph", "elements"),
        Output("JaalGraph", "layout"),
        Output("JaalGraph", "stylesheet"),
        Output("JaalStatus", "children"),
        Output("JaalViewerCardDetails", "open"),
        Input("btn_JaalViewer", "n_clicks"),
        Input("btn_JaalViewerExpand", "n_clicks"),
        Input("btn_JaalViewerFull", "n_clicks"),
        Input("btn_JaalViewerClear", "n_clicks"),
        State("JaalRoot", "value"),
        State("JaalDepth", "value"),
        State("JaalMaxNodes", "value"),
        State("JaalAllowFull", "value"),
        State("JaalGraph", "tapNodeData"),
        State("JaalGraph", "elements"),
        prevent_initial_call=True,
    )
    def update_tree(_draw, _expand, _full, _clear, root, depth, max_nodes,
                    confirmation, node, old_elements):
        try:
            return render_action(ctx.triggered_id, root=root, depth=depth,
                                 max_nodes=max_nodes, confirmed=confirmation,
                                 selected_node=node, previous_elements=old_elements)
        except (ValueError, OSError, csv.Error) as exc:
            return no_update, no_update, no_update, f"未繪製：{exc}", no_update

    @app.callback(
        Output("JaalSelected", "children"),
        Input("JaalGraph", "tapNodeData"),
        prevent_initial_call=True,
    )
    def show_selection(node):
        if not node:
            return "尚未選取節點。"
        name = node.get("id", "")
        ct = node.get("ct", "")
        return f"已選取：{name}" + (f"／{ct}" if ct and ct != name else "")
