"""Real Windows Chromium smoke for the read-only Stage 4 Jaal-only entrypoint.

This starts the actual Dash Jaal-only UI, clicks Load in the parent app, then
inspects the actual visdcc Network inside the on-demand SAME-port child iframe.
It does not activate the model, Stage 4 WorkPool, or modify taxonomy CSVs.
"""
from __future__ import annotations

import argparse
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
    log_file = evidence / "stage4-jaal-only-server.log"
    with log_file.open("w", encoding="utf-8") as output:
        child = subprocess.Popen(
            [sys.executable, str(ROOT / "BertScript" / "Test_result_Vis.py"),
             "--viewer-only", "-p", str(port)],
            cwd=str(ROOT), stdout=output, stderr=subprocess.STDOUT,
        )
        try:
            host = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise AssertionError(f"Jaal-only process exited {child.returncode}")
                try:
                    with urlopen(host + "/_dash-layout", timeout=3) as r:
                        if r.status == 200:
                            break
                except (OSError, URLError):
                    time.sleep(0.5)
            else:
                raise AssertionError("Jaal-only parent Dash never became ready")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                browser_errors = []
                page.on("pageerror", lambda error: browser_errors.append(str(error)))
                page.goto(host + "/", wait_until="domcontentloaded", timeout=60000)
                # Dash mounts React controls asynchronously after index HTML
                # loads. Wait for the real parent app, not just DOMContentLoaded.
                page.locator("#btn_JaalOriginalLoad").wait_for(
                    state="visible", timeout=90000
                )
                assert page.locator("#JaalOriginalRoot").count() == 1
                assert page.locator("#btn_JaalOriginalLoad").count() == 1
                assert page.locator(".jaal-original-iframe").count() == 0, (
                    "Stage 4 must not construct a Jaal iframe until explicit Load"
                )
                page.locator("#btn_JaalOriginalLoad").click()
                iframe = page.locator(".jaal-original-iframe")
                iframe.wait_for(state="visible", timeout=90000)
                src = iframe.get_attribute("src")
                assert src and src.startswith("/jaal-original/") and src.endswith("/")
                assert "://" not in src and ":8053" not in src
                frame = page.frame_locator(".jaal-original-iframe")
                # A failed lazy Jaal build returns 503 with a generic message
                # inside the same-origin iframe. Fail with that reason promptly,
                # rather than a misleading two-minute missing-canvas timeout.
                page.wait_for_function("""() => {
                    const iframe = document.querySelector('.jaal-original-iframe');
                    const body = iframe?.contentDocument?.body;
                    if (!body) return false;
                    if (body.innerText?.includes('原版 Jaal 載入失敗')) return true;
                    return !!body.querySelector('.vis-network canvas');
                }""", timeout=120000)
                failure = frame.locator("body").inner_text(timeout=10000)
                if "原版 Jaal 載入失敗" in failure:
                    raise AssertionError("Real Stage 4 iframe returned lazy-build 503: " + failure[:500])
                canvas = frame.locator(".vis-network canvas").first
                canvas.wait_for(state="visible", timeout=20000)
                dims = canvas.bounding_box()
                assert dims and dims["width"] > 100 and dims["height"] > 100
                assert frame.locator("#jaal-original-layout-mode input[type=radio]").count() == 4
                assert frame.locator("#search_graph").count() == 1
                assert frame.locator("#jaal-original-sidebar-toggle").count() == 1
                page.screenshot(path=str(evidence / "01-stage4-loaded.png"), full_page=True)

                # Test-only wrapper captures the actual rendered visdcc Network
                # instance. No changes are made to shipped runtime assets.
                frame.locator("body").evaluate("""() => {
                    const api = window.dash_clientside?.jaal_structural_collapse;
                    if (!api || typeof api.activate !== 'function') {
                        throw new Error('Installed structural collapse asset missing');
                    }
                    const activate = api.activate;
                    api.activate = function(...args) {
                        window.__stage4JaalNetwork = this;
                        return activate.apply(this, args);
                    };
                }""")

                def choose(label: str) -> None:
                    radio = frame.get_by_label(label, exact=True)
                    radio.check(timeout=25000)
                    assert radio.is_checked()

                def state():
                    return frame.locator("body").evaluate("""() => {
                        const c = window.__stage4JaalNetwork;
                        if (!c?.nn || !c?.ee) return null;
                        return {
                            nodes: c.nn.get(), edges: c.ee.get(),
                            original: c.props?.data?.nodes ?? [],
                            scale: c.net?.getScale?.() ?? null,
                            // This is the vis-network LayoutEngine itself,
                            // not just a Dash radio value or pending React prop.
                            // The actual vis-network LayoutEngine is stored
                            // at net.layoutEngine (not body.modules.layoutEngine
                            // in the installed visdcc runtime).
                            hierarchical: c.net?.layoutEngine
                                ?.options?.hierarchical?.enabled ?? null,
                            layoutOptions: {
                                fromLayoutEngine: c.net?.body?.modules?.layoutEngine?.options?.hierarchical ?? null,
                                fromNetLayoutEngine: c.net?.layoutEngine?.options?.hierarchical ?? null,
                                fromBodyOptions: c.net?.body?.options?.layout?.hierarchical ?? null,
                                fromNetworkOptions: c.net?.options?.layout?.hierarchical ?? null,
                                fromComponentProps: c.props?.options?.layout?.hierarchical ?? null,
                            },
                            structural: {
                                mode: c.__jaalStructural?.mode ?? null,
                                compactActive: c.__jaalStructural?.compactActive ?? null,
                                expandedCount: c.__jaalStructural?.expanded?.size ?? null,
                            },
                            hiddenCount: c.nn.get().filter(n => n.hidden).length,
                        };
                    }""")

                def until(description, predicate):
                    latest = None
                    limit = time.monotonic() + 35
                    while time.monotonic() < limit:
                        latest = state()
                        if latest is not None and predicate(latest):
                            return latest
                        page.wait_for_timeout(250)
                    diagnostic = None if latest is None else {
                        "node_count": len(latest["nodes"]),
                        "original_count": len(latest["original"]),
                        "edge_count": len(latest["edges"]),
                        "hidden_count": latest["hiddenCount"],
                        "sample_labels": [n.get("label") for n in latest["nodes"][:6]],
                        "hierarchical": latest["hierarchical"],
                        "layoutOptions": latest["layoutOptions"],
                        "structural": latest["structural"],
                    }
                    raise AssertionError(f"{description} not observed: {diagnostic!r}")

                choose("網狀（收攏）")
                collapsed = until(
                    "real visdcc collapsed mode initialized",
                    lambda s: len(s["nodes"]) > 0
                    and len(s["original"]) > 0
                    and len(s["nodes"]) == len(s["original"]),
                )
                assert all(isinstance(n["id"], str) for n in collapsed["nodes"])

                # A real mouse drag against the actual vis-network canvas,
                # not a synthetic DataSet update or imperative moveNode().
                # Freeze physics first to make moved positions deterministic.
                frame.locator("body").evaluate("""() => {
                    const net = window.__stage4JaalNetwork.net;
                    net.stopSimulation();
                    net.focus('TW Affairs', {scale: 1, animation: false});
                }""")
                def root_geometry():
                    return frame.locator("body").evaluate("""() => {
                        const net = window.__stage4JaalNetwork.net;
                        const node = net.getPositions(['TW Affairs'])['TW Affairs'];
                        if (!node) throw new Error('Root missing from actual vis-network');
                        return {
                            node, point: net.canvasToDOM(node),
                            view: net.getViewPosition(), scale: net.getScale(),
                        };
                    }""")
                # Verify a real node hit, dragStart AND dragEnd (not only
                # physics drift). Camera/zoom and >15 world-unit thresholds
                # remain unchanged. Use bounded attempts for headless layout.
                frame.locator("body").evaluate("""() => {
                    const net = window.__stage4JaalNetwork.net;
                    window.__stage4RealDragEvents = [];
                    for (const type of ['dragStart', 'dragEnd']) {
                        net.on(type, event => window.__stage4RealDragEvents.push({
                            type, nodes: Array.isArray(event.nodes) ? [...event.nodes] : []
                        }));
                    }
                }""")
                drag_diagnostics = []
                for attempt, (dx, dy) in enumerate(
                    ((75, 35), (95, 45), (115, 50), (130, 60), (145, 65)), 1
                ):
                    frame.locator("body").evaluate("""() => {
                        const net = window.__stage4JaalNetwork.net;
                        // Freeze physics explicitly; stopSimulation alone
                        // does not prevent Jaal from restarting movement
                        // during or immediately after the mouse gesture.
                        // This changes only this browser test instance.
                        net.setOptions({physics: {enabled: false}});
                        net.stopSimulation();
                        net.selectNodes(['TW Affairs']);
                        net.focus('TW Affairs', {scale: 1.5, animation: false});
                        net.stopSimulation();
                        window.__stage4RealDragEvents = [];
                    }""")
                    page.wait_for_timeout(180)
                    before_drag = root_geometry()
                    hit = frame.locator("body").evaluate("""() => {
                        const net = window.__stage4JaalNetwork.net;
                        const root = net.getPositions(['TW Affairs'])['TW Affairs'];
                        return net.getNodeAt(net.canvasToDOM(root));
                    }""")
                    if hit != "TW Affairs":
                        drag_diagnostics.append((attempt, "wrong hit", str(hit)))
                        continue
                    canvas_rect = canvas.bounding_box()
                    assert canvas_rect, "Missing live Jaal canvas for drag"
                    mouse_x = canvas_rect["x"] + before_drag["point"]["x"]
                    mouse_y = canvas_rect["y"] + before_drag["point"]["y"]
                    assert (canvas_rect["x"] + 10 < mouse_x <
                            canvas_rect["x"] + canvas_rect["width"] - 10)
                    assert (canvas_rect["y"] + 10 < mouse_y <
                            canvas_rect["y"] + canvas_rect["height"] - 10)
                    page.mouse.move(mouse_x, mouse_y)
                    page.wait_for_timeout(130)
                    page.mouse.down()
                    page.wait_for_timeout(90)
                    page.mouse.move(mouse_x + dx, mouse_y + dy, steps=28)
                    page.mouse.up()
                    page.wait_for_timeout(260)
                    after_drag = root_geometry()
                    drag_events = frame.locator("body").evaluate(
                        "() => window.__stage4RealDragEvents || []"
                    )
                    real_start = any(
                        e.get("type") == "dragStart"
                        and "TW Affairs" in e.get("nodes", [])
                        for e in drag_events
                    )
                    real_end = any(
                        e.get("type") == "dragEnd"
                        and "TW Affairs" in e.get("nodes", [])
                        for e in drag_events
                    )
                    distance = (
                        (after_drag["node"]["x"] - before_drag["node"]["x"]) ** 2
                        + (after_drag["node"]["y"] - before_drag["node"]["y"]) ** 2
                    ) ** 0.5
                    view_delta = (
                        (after_drag["view"]["x"] - before_drag["view"]["x"]) ** 2
                        + (after_drag["view"]["y"] - before_drag["view"]["y"]) ** 2
                    ) ** 0.5
                    scale_delta = abs(after_drag["scale"] - before_drag["scale"])
                    drag_diagnostics.append((
                        attempt, round(distance, 2), round(view_delta, 2),
                        round(scale_delta, 3), real_start, real_end
                    ))
                    if (real_start and real_end and distance > 15
                            and view_delta < 5 and scale_delta < 0.01):
                        break
                else:
                    raise AssertionError(
                        "Real Jaal node drag/camera acceptance failed "
                        f"after 5 hit-tested mouse gestures; "
                        f"(attempt, move, camera, zoom, dragStart, dragEnd): "
                        f"{drag_diagnostics!r}"
                    )
                page.screenshot(path=str(evidence / "02-stage4-node-drag.png"),
                                full_page=True)
                checkbox = frame.locator("#jaal-original-chinese-labels input[type=checkbox]")
                checkbox.check()
                choose("網狀（全展開）")
                chinese = until(
                    "real Jaal node labels translated while IDs remain literal",
                    lambda s: len(s["nodes"]) == len(s["original"])
                    and any(n.get("label") != n["id"] for n in s["nodes"]),
                )
                assert {n["id"] for n in chinese["nodes"]} == {
                    n["id"] for n in chinese["original"]
                }
                page.screenshot(path=str(evidence / "02-stage4-chinese.png"), full_page=True)

                search = frame.locator("#search_graph")
                search.fill("TW Affairs")
                searched = until(
                    "real Stage 4 Search hidden flags",
                    lambda s: sum(not n.get("hidden") for n in s["nodes"]) == 1
                    and len(s["nodes"]) > 2
                    and any(n["id"] == "TW Affairs" and not n.get("hidden")
                            for n in s["nodes"]),
                )
                assert all(n.get("hidden") for n in searched["nodes"]
                           if n["id"] != "TW Affairs")
                page.screenshot(path=str(evidence / "03-stage4-search.png"), full_page=True)
                search.fill("")
                until("Search reset restores nodes",
                      lambda s: all(not n.get("hidden") for n in s["nodes"]))

                # Exercise real original Jaal Dash callbacks through native
                # browser controls, observe live visdcc DataSets and restoration.
                clean = until(
                    "full graph restored before Filter/Color/Size",
                    lambda s: len(s["nodes"]) == 77
                    and len(s["edges"]) > 10
                    and all(not n.get("hidden") for n in s["nodes"]),
                )
                original_nodes = {n["id"] for n in clean["nodes"]}
                original_edges = {str(e["id"]) for e in clean["edges"]}
                original_edge_count = len(clean["edges"])

                frame.locator("#filter-show-toggle-button").click()
                node_query = frame.locator("#filter_nodes")
                node_query.wait_for(state="visible", timeout=10000)
                node_query.fill("id == 'TW Affairs'")
                node_filtered = until(
                    "pandas node Filter restricts real DataSet",
                    lambda s: {n["id"] for n in s["nodes"]} == {"TW Affairs"},
                )
                assert len(node_filtered["nodes"]) == 1
                page.screenshot(path=str(evidence / "07-stage4-filter-nodes.png"),
                                full_page=True)
                node_query.fill("")
                until(
                    "node Filter reset restores exact original IDs",
                    lambda s: {n["id"] for n in s["nodes"]} == original_nodes,
                )

                edge_query = frame.locator("#filter_edges")
                edge_query.fill(f"{chr(96)}from{chr(96)} == 'TW Affairs'")
                edge_filtered = until(
                    "pandas edge Filter restricts real DataSet",
                    lambda s: 0 < len(s["edges"]) < original_edge_count
                    and all(e["from"] == "TW Affairs" for e in s["edges"]),
                )
                assert {n["id"] for n in edge_filtered["nodes"]} == original_nodes
                edge_query.fill("")
                until(
                    "edge Filter reset restores exact original edge IDs",
                    lambda s: {str(e["id"]) for e in s["edges"]} == original_edges,
                )
                frame.locator("#filter-show-toggle-button").click()
                node_query.wait_for(state="hidden", timeout=10000)

                def node_color(row):
                    color = row.get("color")
                    return color if isinstance(color, str) else str(color)

                def edge_color(row):
                    color = row.get("color")
                    if isinstance(color, dict):
                        return color.get("color")
                    return color

                color_baseline = state()
                baseline_node_colors = {
                    n["id"]: node_color(n) for n in color_baseline["nodes"]
                }
                baseline_edge_colors = {
                    str(e["id"]): edge_color(e) for e in color_baseline["edges"]
                }
                frame.locator("#color_nodes").select_option("Positivity")
                colored_nodes = until(
                    "Color nodes by real Positivity metadata",
                    lambda s: {n["id"] for n in s["nodes"]} == original_nodes
                    and any(node_color(n) != baseline_node_colors[n["id"]]
                            for n in s["nodes"]),
                )
                assert all(n.get("color") for n in colored_nodes["nodes"])
                frame.locator("#color-legend-toggle").click()
                frame.locator("#color-legend-popup").wait_for(
                    state="visible", timeout=12000
                )
                page.screenshot(path=str(evidence / "08-stage4-color-legend.png"),
                                full_page=True)
                frame.locator("#color-legend-toggle").click()
                frame.locator("#color_nodes").select_option("None")
                until(
                    "node Color reset restores default blue",
                    lambda s: all(node_color(n) == "#97C2FC"
                                  for n in s["nodes"]),
                )

                frame.locator("#color_edges").select_option("strength")
                until(
                    "Color edges by original categorical strength",
                    lambda s: {str(e["id"]) for e in s["edges"]} == original_edges
                    and any(edge_color(e) != baseline_edge_colors[str(e["id"])]
                            for e in s["edges"]),
                )
                frame.locator("#color_edges").select_option("None")
                until(
                    "edge Color reset restores default blue",
                    lambda s: all(edge_color(e) == "#97C2FC"
                                  for e in s["edges"]),
                )

                frame.locator("#size_nodes").select_option("Degree")
                sized_nodes = until(
                    "Size nodes by actual numeric Degree",
                    lambda s: {n["id"] for n in s["nodes"]} == original_nodes
                    and any(float(n.get("size", 7)) > 7
                            for n in s["nodes"]),
                )
                assert all(float(n["size"]) >= 7 for n in sized_nodes["nodes"])
                frame.locator("#size_nodes").select_option("None")
                until(
                    "node Size reset restores default 7",
                    lambda s: all(float(n.get("size", 0)) == 7
                                  for n in s["nodes"]),
                )
                frame.locator("#size_edges").select_option(
                    "endpoint_LGPdepth_weight"
                )
                until(
                    "Size edges by original numeric endpoint depth weight",
                    lambda s: {str(e["id"]) for e in s["edges"]} == original_edges
                    and any(float(e.get("width", 1)) > 1
                            for e in s["edges"]),
                )
                page.screenshot(path=str(evidence / "09-stage4-size-edges.png"),
                                full_page=True)
                frame.locator("#size_edges").select_option("None")
                until(
                    "edge Size reset restores default 1",
                    lambda s: all(float(e.get("width", 0)) == 1
                                  for e in s["edges"]),
                )
                fully_reset = state()
                assert {n["id"] for n in fully_reset["nodes"]} == original_nodes
                assert {str(e["id"]) for e in fully_reset["edges"]} == original_edges
                assert not any(n.get("hidden") for n in fully_reset["nodes"])
                toggle = frame.locator("#jaal-original-sidebar-toggle")
                toggle.click()
                frame.locator("#jaal-original-settings-column").wait_for(state="hidden")
                assert canvas.is_visible()
                page.screenshot(path=str(evidence / "04-stage4-sidebar-collapsed.png"),
                                full_page=True)
                toggle.click()
                frame.locator("#jaal-original-settings-column").wait_for(state="visible")
                checkbox.uncheck()
                choose("階層（收攏）")
                until(
                    "actual collapsed hierarchy renders in vis-network",
                    lambda s: s["hierarchical"] is True
                    and 0 < len(s["nodes"]) < len(s["original"]),
                )
                assert canvas.is_visible()
                page.screenshot(path=str(evidence / "05-stage4-hierarchy-collapsed.png"),
                                full_page=True)
                choose("階層（全展開）")
                until(
                    "real expanded hierarchy restores all original IDs",
                    lambda s: s["hierarchical"] is True
                    and len(s["nodes"]) == len(s["original"])
                    and {n["id"] for n in s["nodes"]}
                    == {n["id"] for n in s["original"]},
                )
                page.screenshot(path=str(evidence / "06-stage4-hierarchy-expanded.png"),
                                full_page=True)
                choose("網狀（全展開）")
                restored = until(
                    "hierarchy disabled and original IDs/English labels restored",
                    lambda s: s["hierarchical"] is False
                    and len(s["nodes"]) == len(s["original"])
                    and all(n["label"] == n["id"] and not n.get("hidden")
                            for n in s["nodes"]),
                )
                assert len(restored["nodes"]) > 2
                assert not browser_errors, "Browser JS errors: " + " | ".join(browser_errors)
                (evidence / "verified-scope.txt").write_text(
                    "PASS: hosted Windows Chromium opened actual --viewer-only Stage 4 "
                    "Dash, explicitly loaded original Jaal same-port iframe, exercised "
                    "all four modes including real collapsed/expanded hierarchy, checked live visdcc Search hidden flags and Chinese "
                    "labels, real canvas drag without camera pan, real Filter/Color/Size node/edge callbacks and resets, sidebar toggle and original ID restoration.\n"
                    "NOT VERIFIED: human Windows GPU/model/WorkPool, manual motion/focus perception, "
                    "uncovered Color/Size/Filter combinations, user screen layout "
                    "and complete Dash version matrix.\n",
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
    parser.add_argument("--port", type=int, default=8097)
    parser.add_argument("--evidence", type=Path, default=Path("stage4-browser-evidence"))
    args = parser.parse_args()
    run(args.port, args.evidence)
