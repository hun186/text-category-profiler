"""Extra Stage 4 card containing the historic Jaal UI, on the same port."""
from __future__ import annotations

from dash import Input, Output, State, dcc, html, no_update
import dash_bootstrap_components as dbc

from BertScript.jaal_original_mount import OriginalJaalRouter, DEFAULT_ROOT

router = OriginalJaalRouter()


def build_original_jaal_panel():
    """Visible control panel, zero Jaal initialization and no iframe initially."""
    return dbc.Card([
        dbc.CardHeader(html.H3("原版 Jaal 進階檢視器｜完整搜尋、篩選、顏色與大小設定")),
        dbc.CardBody([
            html.P("保留原版 Jaal / vis.js 的互動外觀與進階控制。"
                   "此區塊與上方的輕量分類樹互相獨立；"
                   "只有按下「載入原版 Jaal」才建立圖形與其回呼。"),
            html.Div([
                html.Label("根類別（英文 ClassLabel）"),
                dcc.Input(id="JaalOriginalRoot", type="text", value=DEFAULT_ROOT,
                          debounce=True, style={"minWidth": "300px"}),
                html.Button("載入原版 Jaal", id="btn_JaalOriginalLoad",
                            n_clicks=0),
            ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap",
                      "alignItems": "center"}),
            dcc.Checklist(
                id="JaalOriginalLargeConsent", value=[],
                options=[{"label": "大型子樹：我知道可能耗用較多瀏覽器／伺服器資源",
                          "value": "yes"}],
            ),
            html.P("預設最多 250 個節點；大型子樹須先勾選確認，"
                   "絕不在進入主頁時自動全畫。"),
            html.Div(id="JaalOriginalStatus", role="status",
                     children="尚未載入原版 Jaal；主站不需啟動 8053 port。"),
            html.Div(id="JaalOriginalFrame"),
        ]),
    ], style={"width": "100%", "margin": "16px 0"})


def register_original_jaal(app):
    router.mount(app.server)

    @app.callback(
        Output("JaalOriginalFrame", "children"),
        Output("JaalOriginalStatus", "children"),
        Input("btn_JaalOriginalLoad", "n_clicks"),
        State("JaalOriginalRoot", "value"),
        State("JaalOriginalLargeConsent", "value"),
        prevent_initial_call=True,
    )
    def load_original_jaal(clicks, root, consent):
        if not clicks:
            return no_update, no_update
        try:
            src, stats = router.prepare(
                root, confirmed_large=("yes" in (consent or []))
            )
        except (ValueError, OSError) as exc:
            return no_update, f"原版 Jaal 尚未載入：{exc}"
        return (
            html.Iframe(
                src=src,
                style={"width": "100%", "height": "1100px",
                       "border": "1px solid #cbd5e1"},
                title="原版 Jaal 分類樹進階操作",
            ),
            f"已要求載入：{stats['root']}；"
            f"{stats['nodes']:,} 個節點／{stats['edges']:,} 條關係。"
            "原版 Jaal 的 Search／Filter／Color／Size 在下方窗格操作。",
        )
