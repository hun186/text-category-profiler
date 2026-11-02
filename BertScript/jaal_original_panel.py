"""Extra Stage 4 card containing the historic Jaal UI, on the same port."""
from __future__ import annotations

from dash import Input, Output, State, dcc, html, no_update
import dash_bootstrap_components as dbc

from BertScript.jaal_original_mount import OriginalJaalRouter, DEFAULT_ROOT

router = OriginalJaalRouter()


def build_original_jaal_panel():
    """Visible control panel, zero Jaal initialization and no iframe initially."""
    return dbc.Card([
        dbc.CardHeader(html.H3("Jaal 進階檢視器｜搜尋、篩選、顏色、大小與版型")),
        dbc.CardBody([
            html.P("保留 Jaal / vis.js 的互動外觀與進階控制。"
                   "此區塊與上方的輕量分類樹互相獨立；"
                   "只有按下「載入 Jaal」才建立圖形與其回呼。"),
            html.Div([
                html.Label(
                    "根類別（英文 ClassLabel）：",
                    htmlFor="JaalOriginalRoot",
                    style={"whiteSpace": "nowrap", "marginBottom": "0"},
                ),
                dcc.Input(
                    id="JaalOriginalRoot", type="text", value=DEFAULT_ROOT,
                    debounce=True,
                    style={
                        # Do not let a global form-control width:100% turn
                        # this into an otherwise empty full-width row.
                        "width": "320px", "maxWidth": "100%", "minWidth": "0",
                        "flex": "0 1 320px",
                    },
                ),
                html.Button("載入 Jaal", id="btn_JaalOriginalLoad",
                            n_clicks=0),
            ], style={"display": "flex", "gap": "10px", "flexWrap": "wrap",
                      "alignItems": "center", "marginBottom": "8px"}),
            dcc.Checklist(
                id="JaalOriginalLargeConsent", value=[],
                options=[{"label": "大型子樹：我知道可能耗用較多瀏覽器／伺服器資源",
                          "value": "yes"}],
            ),
            html.P("預設最多 250 個節點；大型子樹須先勾選確認，"
                   "絕不在進入主頁時自動全畫。"),
            html.Div(id="JaalOriginalStatus", role="status",
                     children="尚未載入 Jaal"),
            html.Div(id="JaalOriginalFrame"),
        ]),
    ], style={"width": "100%", "margin": "16px 0"})


def build_original_jaal_iframe(src):
    """Render a same-origin iframe; the child sizes it to actual Jaal content.

    The initial 800px height remains usable if browser JS cannot run.
    """
    return html.Iframe(
        src=src,
        className="jaal-original-iframe",
        style={
            "width": "100%",
            "height": "800px",
            "display": "block",
            "border": "1px solid #cbd5e1",
        },
        title="Jaal 分類樹進階操作",
    )


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
            return no_update, f"Jaal 尚未載入：{exc}"
        return (
            build_original_jaal_iframe(src),
            f"已要求載入：{stats['root']}；"
            f"{stats['nodes']:,} 個節點／{stats['edges']:,} 條關係。"
            "Jaal 的 Search／Filter／Color／Size 與網狀／階層模式在下方窗格操作。",
        )
