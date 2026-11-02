"""Launch precomputed Stage 4 history as a separate loopback-only Dash page.

Unlike the 4,000-line production Stage 4, this entry point never invokes
visualization_stage, training, WorkPool picker or report exporters. It does not
claim to restore all legacy analytical charts.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from BertScript.stage4_history_data import (
    DATABASES, HistoryPreviewError, list_tables, list_workspaces,
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


def build_app(workpool):
    from dash import Dash, Input, Output, dcc, html, dash_table
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
                      "value": "yes"}]),
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
        html.H3("分類樹與 Jaal（獨立於歷史結果）"),
        build_tree_panel(),
        build_original_jaal_panel(),
    ], style={"maxWidth": "1500px", "margin": "0 auto",
              "padding": "18px", "fontFamily": "sans-serif"})

    @app.callback(
        Output("HistoryTable", "options"),
        Output("HistoryTable", "value"),
        Output("HistoryStatus", "children"),
        Input("HistoryWorkspace", "value"),
        Input("HistoryDatabase", "value"),
        Input("HistoryConfirmRunning", "value"),
    )
    def choose_table(workspace, database, consent):
        if not workspace:
            return [], None, "WorkPool 沒有可選的歷史結果資料夾。"
        try:
            info = select_workspace(root, workspace)
            prefix = (
                "狀態：已完成；" if info.complete else
                "狀態：可能執行中或中斷；未宣告完成；"
            )
            tables = list_tables(root, workspace, database,
                                 confirm_running="yes" in (consent or []))
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
        Input("HistoryWorkspace", "value"),
        Input("HistoryDatabase", "value"),
        Input("HistoryTable", "value"),
        Input("HistoryPage", "value"),
        Input("HistoryConfirmRunning", "value"),
    )
    def show_page(workspace, database, table, page, consent):
        if not workspace or not table:
            return [], [], "請先選擇可讀取的資料表。"
        try:
            page_data = read_page(
                root, workspace, database, table, page,
                confirm_running="yes" in (consent or []),
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
