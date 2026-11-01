"""Read-only Jaal GUI launcher, deliberately independent of Stage 4 WorkPool.

This launcher is for exploring TopicTree via the already existing same-port
embedded Jaal card. It does NOT reopen Stage 4 analysis tables/reports and
must not call datasetDirOutputDirPickers or visualization_stage lifecycle.
"""
from __future__ import annotations

import argparse


def parse_viewer_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "只啟動 Jaal 圖形檢視介面；不掃描、改名或處理 WorkPool。"
            "不包含 Stage 4 分析表格及報告。"
        )
    )
    parser.add_argument(
        "--viewer-only", action="store_true", required=True,
        help="啟動獨立的 Jaal 唯讀檢視器（不執行 Stage 4 工作流程）",
    )
    parser.add_argument(
        "-p", "--port", type=int, default=8059,
        help="本機 Jaal 網頁 port（預設 8059）",
    )
    parsed = parser.parse_args(argv)
    if not 1 <= parsed.port <= 65535:
        parser.error("port must be within 1..65535")
    return parsed


def build_viewer_only_app():
    """Only create a lazy Jaal panel; never load any WorkPool/model outputs."""
    from BertScript.visualization_stage import import_dash_runtime
    from BertScript.jaal_original_panel import (
        build_original_jaal_panel, register_original_jaal,
    )

    dash = import_dash_runtime()
    app = dash.Dash(__name__)
    app.layout = build_original_jaal_panel()
    register_original_jaal(app)
    return app


def main(argv=None):
    args = parse_viewer_args(argv)
    app = build_viewer_only_app()
    print(
        f"Jaal viewer only: http://127.0.0.1:{args.port}/ "
        "(loopback, read-only; Stage 4 WorkPool unchanged)",
        flush=True,
    )
    run = app.run if hasattr(app, "run") else app.run_server
    run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
