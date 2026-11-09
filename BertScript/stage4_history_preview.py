"""Launch precomputed Stage 4 history as a separate loopback-only Dash page.

Unlike the 4,000-line production Stage 4, this entry point never invokes
visualization_stage, training, WorkPool picker or report exporters. It does not
claim to restore all legacy analytical charts.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from BertScript.stage4_history_data import (
    DATABASES, DISTRIBUTION_SAMPLE_ROWS, HistoryPreviewError,
    list_columns, list_tables, list_workspaces, read_distribution,
    read_page, select_workspace,
)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Stage 4 歷史結果唯讀預覽：選擇資料集、查看已儲存 SQL 表格與 Jaal。"
    )
    parser.add_argument("--history-preview", action="store_true", required=True)
    parser.add_argument("--workpool", default="WorkPool")
    parser.add_argument("-p", "--port", type=int, default=8060)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    return args


def _consent_transition(workspace, checked, previous, triggered):
    """Do not reuse acknowledgement across interrupted workspace selections."""
    previous = previous if isinstance(previous, dict) else {}
    if (triggered != "HistoryConfirmRunning"
            or previous.get("workspace") != workspace):
        return {"workspace": workspace, "confirmed": False}, []
    approved = bool(workspace and workspace in (checked or []))
    return {"workspace": workspace, "confirmed": approved}, (
        [workspace] if approved else []
    )


def _preferred_distribution_column(columns):
    """Choose a useful persisted classification field before generic IDs/text."""
    for candidate in ("ClassLabel", "Label", "classLabels", "Topic", "Category"):
        for value in columns:
            if value.lower() == candidate.lower():
                return value
    return next((value for value in columns if value.lower() not in
                 ("index", "id", "rowid", "text", "content", "body", "url")),
                columns[0] if columns else None)


def _distribution_chart(payload):
    """Small Plotly figure from the already bounded, read-only SQLite sample."""
    groups = list(reversed(payload["categories"]))
    count = len(groups)
    return {
        "data": [{
            "type": "bar", "orientation": "h",
            "x": [g["count"] for g in groups],
            "y": [g["label"] for g in groups],
            "hovertemplate": "%{y}: %{x} 筆<extra></extra>",
        }] if groups else [],
        "layout": {
            "height": max(290, 75 + 34 * count),
            "margin": {"l": 260, "r": 24, "t": 30, "b": 50},
            "xaxis": {"title": "樣本筆數", "rangemode": "tozero"},
            "yaxis": {"automargin": True, "type": "category"},
            "showlegend": False,
        },
    }


def build_app(workpool):
    from dash import Dash, Input, Output, State, ctx, dcc, html, dash_table
    from BertScript.jaal_original_panel import (
        build_original_jaal_panel, register_original_jaal,
    )
    from BertScript.embedded_tree_panel import (
        build_tree_panel, register_tree_callbacks,
    )

    root = Path(workpool).resolve(strict=True)
    if not root.is_dir():
        raise HistoryPreviewError("WorkPool is not a directory")
    candidates = list_workspaces(root)
    ready = next((w for w in candidates if w.complete), None)
    selected = (ready or candidates[0]).name if candidates else None
    labels = []
    for info in candidates:
        label = ("已完成" if info.complete else
                 "執行中／曾中斷" if info.status == "is_running_TestResultVis" else
                 "結果不完整")
        if info.missing:
            label += "（缺：" + ", ".join(info.missing) + "）"
        labels.append({"label": info.name + "｜" + label, "value": info.name})

    app = Dash(__name__)
    app.title = "Stage 4 歷史結果唯讀預覽"
    app.layout = html.Div([
        html.H2("Stage 4｜已存結果預覽（唯讀）"),
        html.P("這是安全的歷史檢視入口，不是原版 Stage 4 的完整計算介面。"
               "提供已存 SQLite 資料表和原有 Jaal；不重算、寫回、改名、"
               "推進 WorkPool 階段，也不啟動模型。"),
        html.P("注意：_is_running_TestResultVis 不代表已完成；"
               "請先確認沒有其他程式正在處理該資料夾。"),
        html.Label("歷史資料集"),
        dcc.Dropdown(id="HistoryWorkspace", options=labels, value=selected,
                     searchable=True, clearable=False),
        dcc.Checklist(
            id="HistoryConfirmRunning", value=[],
            options=[{"label": "我已確認所選的 _is_running_TestResultVis 資料集"
                       "沒有其他程序正在寫入，了解結果可能不完整",
                      "value": selected or ""}]),
        dcc.Store(id="HistoryAuthorization",
                  data={"workspace": None, "confirmed": False}),
        html.Div(id="HistoryStatus", role="status"),
        html.Div([
            html.Div([
                html.Label("已儲存的資料庫"),
                dcc.Dropdown(id="HistoryDatabase", value=DATABASES[0],
                             options=[{"label": x, "value": x} for x in DATABASES],
                             clearable=False),
            ], style={"flex": "2 1 260px"}),
            html.Div([
                html.Label("資料表"),
                dcc.Dropdown(id="HistoryTable", options=[], value=None,
                             clearable=False),
            ], style={"flex": "2 1 260px"}),
            html.Div([
                html.Label("頁碼（每頁最多 50 列）"),
                dcc.Input(id="HistoryPage", type="number", min=1, step=1,
                          value=1, style={"width": "110px"}),
            ], style={"flex": "1 1 150px"}),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                  "marginTop": "12px"}),
        html.Div(id="HistoryPageInfo", role="status",
                 style={"margin": "10px 0"}),
        dash_table.DataTable(
            id="HistoryDataTable",
            data=[], columns=[],
            page_action="none",
            style_table={"overflowX": "auto", "maxWidth": "100%"},
            style_cell={"fontSize": 12, "maxWidth": 360,
                        "overflow": "hidden", "textOverflow": "ellipsis",
                        "textAlign": "left", "whiteSpace": "normal"},
        ),
        html.Hr(),
        html.H3("已儲存結果｜欄位值前綴分布（唯讀）"),
        html.P(
            f"從已儲存 SQLite 最前面最多 {DISTRIBUTION_SAMPLE_ROWS:,} 筆計算欄位值"
            "前 120 字元的出現次數，顯示最多 15 種前綴。"
            "超長值可能因前綴相同被合併，並非完整原始值的精確去重。"
            "資料超出抽樣上限時不代表全量統計；不重新分類、不寫入結果。"
        ),
        html.Label("分析欄位"),
        dcc.Dropdown(id="HistoryDistributionColumn", options=[], value=None,
                     searchable=True, clearable=False),
        html.Div(id="HistoryDistributionInfo", role="status",
                 style={"margin": "10px 0"}),
        dcc.Graph(id="HistoryDistributionPlot",
                  figure=_distribution_chart({"categories": []}),
                  config={"displayModeBar": False}),
        html.Hr(),
        html.H3("分類樹與 Jaal（獨立於歷史結果）"),
        build_tree_panel(),
        build_original_jaal_panel(),
    ], style={"maxWidth": "1500px", "margin": "0 auto",
              "padding": "18px", "fontFamily": "sans-serif"})

    @app.callback(
        Output("HistoryAuthorization", "data"),
        Output("HistoryConfirmRunning", "value"),
        Output("HistoryConfirmRunning", "options"),
        Input("HistoryWorkspace", "value"),
        Input("HistoryConfirmRunning", "value"),
        State("HistoryAuthorization", "data"),
    )
    def reconcile_consent(workspace, checked, previous):
        authorization, checked_next = _consent_transition(
            workspace, checked, previous, ctx.triggered_id,
        )
        return authorization, checked_next, [{
            "label": "我已確認所選的 _is_running_TestResultVis 資料集"
                     "沒有其他程序正在寫入，了解結果可能不完整",
            "value": workspace or "",
        }]

    @app.callback(
        Output("HistoryTable", "options"),
        Output("HistoryTable", "value"),
        Output("HistoryStatus", "children"),
        Input("HistoryAuthorization", "data"),
        Input("HistoryDatabase", "value"),
    )
    def choose_table(authorization, database):
        authorization = authorization or {}
        workspace = authorization.get("workspace")
        if not workspace:
            return [], None, "WorkPool 沒有可選的歷史結果資料夾。"
        try:
            info = select_workspace(root, workspace)
            prefix = (
                "狀態：已完成；" if info.complete else
                "狀態：可能執行中或中斷；未宣告完成；"
            )
            tables = list_tables(root, workspace, database,
                                 confirm_running=authorization.get("confirmed") is True)
            options = [{"label": x, "value": x} for x in tables]
            return options, (tables[0] if tables else None), prefix + (
                f"找到 {len(tables)} 張已儲存的資料表（唯讀）。"
                if tables else "資料庫沒有可顯示的資料表。"
            )
        except (HistoryPreviewError, OSError) as exc:
            return [], None, f"未開啟資料：{exc}"

    @app.callback(
        Output("HistoryDataTable", "columns"),
        Output("HistoryDataTable", "data"),
        Output("HistoryPageInfo", "children"),
        Input("HistoryAuthorization", "data"),
        Input("HistoryDatabase", "value"),
        Input("HistoryTable", "value"),
        Input("HistoryPage", "value"),
    )
    def show_page(authorization, database, table, page):
        authorization = authorization or {}
        workspace = authorization.get("workspace")
        if not workspace or not table:
            return [], [], "請先選擇可讀取的資料表。"
        try:
            page_data = read_page(
                root, workspace, database, table, page,
                confirm_running=authorization.get("confirmed") is True,
            )
        except (HistoryPreviewError, OSError) as exc:
            return [], [], "未讀取： " + str(exc)
        cols = [{"name": name, "id": name} for name in page_data["columns"]]
        extra = "；僅顯示前 24 欄" if page_data["truncated_columns"] else ""
        suffix = "（還有下一頁）" if page_data["has_next"] else "（最後一頁）"
        return cols, page_data["rows"], (
            f"第 {page_data['page']} 頁，{len(page_data['rows'])} 列"
            + suffix + extra + "；文字欄位最多顯示 600 字元。"
        )

    @app.callback(
        Output("HistoryDistributionColumn", "options"),
        Output("HistoryDistributionColumn", "value"),
        Input("HistoryAuthorization", "data"),
        Input("HistoryDatabase", "value"),
        Input("HistoryTable", "value"),
    )
    def choose_distribution_column(authorization, database, table):
        authorization = authorization or {}
        workspace = authorization.get("workspace")
        if not workspace or not table:
            return [], None
        try:
            columns = list_columns(
                root, workspace, database, table,
                confirm_running=authorization.get("confirmed") is True,
            )
            return ([{"label": name, "value": name} for name in columns],
                    _preferred_distribution_column(columns))
        except (HistoryPreviewError, OSError):
            return [], None

    @app.callback(
        Output("HistoryDistributionPlot", "figure"),
        Output("HistoryDistributionInfo", "children"),
        Input("HistoryAuthorization", "data"),
        Input("HistoryDatabase", "value"),
        Input("HistoryTable", "value"),
        Input("HistoryDistributionColumn", "value"),
    )
    def show_distribution(authorization, database, table, column):
        empty = _distribution_chart({"categories": []})
        authorization = authorization or {}
        workspace = authorization.get("workspace")
        if not workspace or not table or not column:
            return empty, "請先選擇資料集、資料表及分析欄位。"
        try:
            payload = read_distribution(
                root, workspace, database, table, column,
                confirm_running=authorization.get("confirmed") is True,
            )
        except (HistoryPreviewError, OSError) as exc:
            return empty, "未顯示分布：" + str(exc)
        sample_note = (
            "；達抽樣上限，後續資料未納入，非全量統計"
            if payload["has_more_rows"] else "；已包含此資料表全部列"
        )
        shown = payload["displayed_groups"]
        distinct = payload["distinct_prefixes"]
        clipped = payload["truncated_values"]
        prefix_warning = (
            f"；有 {clipped:,} 筆超過 120 字，前綴相同的不同原始值可能被合併計數"
            if clipped else "；樣本中沒有超長截斷值"
        )
        return _distribution_chart(payload), (
            f"已讀取 {payload['sampled_rows']:,} 筆；"
            f"樣本中 {distinct:,} 種不同顯示前綴，顯示前 {shown} 種"
            + prefix_warning + sample_note + "。"
        )

    register_tree_callbacks(app)
    register_original_jaal(app)
    return app


def main(argv=None):
    args = parse_args(argv)
    app = build_app(args.workpool)
    print(f"Stage 4 history read-only preview: http://127.0.0.1:{args.port}/",
          flush=True)
    run = app.run if hasattr(app, "run") else app.run_server
    run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
