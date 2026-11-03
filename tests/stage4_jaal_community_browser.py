"""Real Windows Chromium Stage 4 Louvain *opt-in candidate* acceptance.

Starts viewer-only, not the model/WorkPool. Uses the real same-port Jaal iframe
and live visdcc DataSets. Never modifies TopicTree/ClassTable or production pin.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(port: int, evidence: Path) -> None:
    from playwright.sync_api import sync_playwright

    evidence.mkdir(parents=True, exist_ok=True)
    log_file = evidence / "stage4-community-server.log"
    with log_file.open("w", encoding="utf-8") as log:
        environment = dict(os.environ)
        environment["JAAL_STAGE4_COMMUNITY_CANDIDATE"] = "1"
        child = subprocess.Popen(
            [sys.executable, str(ROOT / "BertScript" / "Test_result_Vis.py"),
             "--viewer-only", "-p", str(port)],
            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, env=environment,
        )
        try:
            host = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise AssertionError(f"Candidate Jaal process exited: {child.returncode}")
                try:
                    with urlopen(host + "/_dash-layout", timeout=3) as response:
                        if response.status == 200:
                            break
                except (OSError, URLError):
                    time.sleep(0.5)
            else:
                raise AssertionError("Candidate Stage 4 parent Dash never became ready")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                browser_errors = []
                page.on("pageerror", lambda error: browser_errors.append(str(error)))
                page.goto(host + "/", wait_until="domcontentloaded", timeout=60000)
                page.locator("#btn_JaalOriginalLoad").wait_for(
                    state="visible", timeout=90000
                )
                assert page.locator(".jaal-original-iframe").count() == 0
                page.locator("#btn_JaalOriginalLoad").click()
                iframe = page.locator(".jaal-original-iframe")
                iframe.wait_for(state="visible", timeout=90000)
                src = iframe.get_attribute("src")
                assert src and src.startswith("/jaal-original/") and "://" not in src
                frame = page.frame_locator(".jaal-original-iframe")
                page.wait_for_function("""() => {
                    const box = document.querySelector('.jaal-original-iframe');
                    const doc = box?.contentDocument;
                    return !!(doc?.body?.innerText?.includes('原版 Jaal 載入失敗') ||
                              doc?.querySelector('.vis-network canvas'));
                }""", timeout=120000)
                if "原版 Jaal 載入失敗" in frame.locator("body").inner_text():
                    raise AssertionError("Candidate original Jaal child failed: "
                                         + frame.locator("body").inner_text()[:400])
                canvas = frame.locator(".vis-network canvas").first
                canvas.wait_for(state="visible", timeout=25000)
                assert frame.locator(
                    "#jaal-original-layout-mode input[type=radio]"
                ).count() == 5
                assert frame.locator("#search_graph").count() == 1
                assert frame.locator("#color_nodes").count() == 1
                assert frame.locator("#size_nodes").count() == 1
                assert frame.locator("#jaal-original-sidebar-toggle").count() == 1
                assert frame.locator("#jaal-original-graph-profile").count() == 1
                assert frame.get_by_label(
                    "網狀（社群收攏・Louvain）", exact=True
                ).is_enabled()
                assert "圖形類型：" in frame.locator(
                    "#jaal-original-graph-profile"
                ).inner_text()
                page.screenshot(
                    path=str(evidence / "01-stage4-fifth-mode.png"), full_page=True
                )

                # Capture only the actual mounted visdcc component when its
                # shipped upstream community runtime activates. No mock graph.
                frame.locator("body").evaluate("""() => {
                    const api = window.dash_clientside?.jaal_community_collapse;
                    if (!api || typeof api.activate !== 'function')
                        throw Error("Candidate community JS asset missing");
                    const old = api.activate;
                    api.activate = function(...args) {
                        window.__stage4CommunityNetwork = this;
                        return old.apply(this, args);
                    };
                }""")

                def snapshot():
                    return frame.locator("body").evaluate("""() => {
                        const c = window.__stage4CommunityNetwork;
                        if (!c?.nn || !c?.ee) return null;
                        return {
                            nodes:c.nn.get(), edges:c.ee.get(),
                            originalNodes:c.props.data.nodes,
                            originalEdges:c.props.data.edges,
                            active:!!c.__jaalCommunity?.active,
                            filtered:!!c.__jaalCommunity?.filtered,
                            clusters:Object.keys(c.__jaalCommunity?.view?.clusterToGroup || {}),
                        };
                    }""")

                def until(label, predicate):
                    state = None
                    limit = time.monotonic() + 35
                    while time.monotonic() < limit:
                        state = snapshot()
                        if state is not None and predicate(state):
                            return state
                        page.wait_for_timeout(250)
                    diagnostic = None if state is None else {
                        "nodes": len(state["nodes"]),
                        "edges": len(state["edges"]),
                        "original": len(state["originalNodes"]),
                        "active": state["active"],
                        "filtered": state["filtered"],
                        "clusters": state["clusters"][:5],
                    }
                    raise AssertionError(f"{label}: {diagnostic}")

                frame.get_by_label(
                    "網狀（社群收攏・Louvain）", exact=True
                ).check(timeout=25000)
                collapsed = until(
                    "real visdcc community quotient is smaller than source",
                    lambda s: s["active"] and not s["filtered"]
                    and len(s["nodes"]) < len(s["originalNodes"])
                    and len(s["clusters"]) > 0,
                )
                original_ids = {n["id"] for n in collapsed["originalNodes"]}
                original_edges = {str(e["id"]) for e in collapsed["originalEdges"]}
                assert len(original_ids) > 20, "Expected real TW Affairs taxonomy subtree"
                page.screenshot(
                    path=str(evidence / "02-stage4-community-collapsed.png"),
                    full_page=True,
                )

                # A real Jaal Search event restores original IDs while active
                # then goes back to the same Louvain quotient when cleared.
                search = frame.locator("#search_graph")
                search.fill("TW")
                until(
                    "Search in community mode restores original visdcc IDs",
                    lambda s: s["active"] and s["filtered"]
                    and {n["id"] for n in s["nodes"]} == original_ids
                    and any(n.get("hidden") for n in s["nodes"])
                    and any(not n.get("hidden") for n in s["nodes"]),
                )
                page.screenshot(
                    path=str(evidence / "03-stage4-community-search.png"),
                    full_page=True,
                )
                search.fill("")
                until(
                    "Search reset returns to compact Louvain graph",
                    lambda s: s["active"] and not s["filtered"]
                    and len(s["nodes"]) < len(s["originalNodes"])
                    and len(s["clusters"]) > 0,
                )

                frame.get_by_label("網狀（全展開）", exact=True).check(timeout=25000)
                restored = until(
                    "exiting Louvain restores exact original IDs and directed edges",
                    lambda s: not s["active"]
                    and {n["id"] for n in s["nodes"]} == original_ids
                    and {str(e["id"]) for e in s["edges"]} == original_edges
                    and not any(str(n["id"]).startswith(
                        "__jaal_internal_community__") for n in s["nodes"]),
                )
                assert all(n["id"] == n["label"] and not n.get("hidden")
                           for n in restored["nodes"])
                assert not browser_errors, "Browser JS errors: " + " | ".join(browser_errors)
                page.screenshot(
                    path=str(evidence / "04-stage4-community-restored.png"),
                    full_page=True,
                )
                (evidence / "verified-scope.txt").write_text(
                    "PASS: Hosted Windows Chromium launched actual Stage 4 --viewer-only "
                    "same-port original Jaal with exact upstream opt-in fifth mode, "
                    "observed real visdcc Louvain quotient, live Search restore, "
                    "original IDs and directed edge IDs restored.\n"
                    "NOT VERIFIED: user desktop perception, full ML WorkPool, "
                    "Louvain canvas click expansion, production requirements pin.\n",
                    encoding="utf-8",
                )
                browser.close()
        finally:
            child.terminate()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8098)
    parser.add_argument("--evidence", type=Path,
                        default=Path("stage4-community-browser-evidence"))
    args = parser.parse_args()
    run(args.port, args.evidence)
