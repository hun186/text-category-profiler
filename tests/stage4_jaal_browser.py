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
                canvas = frame.locator(".vis-network canvas").first
                canvas.wait_for(state="visible", timeout=120000)
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
                            hierarchical: c.net?.body?.modules?.layoutEngine
                                ?.options?.hierarchical?.enabled ?? null,
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
                    raise AssertionError(f"{description} not observed: {str(latest)[:1300]}")

                choose("網狀（收攏）")
                collapsed = until(
                    "real visdcc collapsed mode initialized",
                    lambda s: len(s["nodes"]) > 0
                    and len(s["original"]) > 0
                    and len(s["nodes"]) == len(s["original"]),
                )
                assert all(isinstance(n["id"], str) for n in collapsed["nodes"])
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
                    "actual vis-network hierarchy layout active",
                    lambda s: s["hierarchical"] is True
                    and len(s["nodes"]) > 0,
                )
                assert canvas.is_visible()
                page.screenshot(path=str(evidence / "05-stage4-hierarchy.png"),
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
                    "four modes including real hierarchical LayoutEngine, checked live visdcc Search hidden flags and Chinese "
                    "labels, sidebar toggle and original ID restoration.\n"
                    "NOT VERIFIED: human Windows GPU/model/WorkPool, precise drag/camera "
                    "perception, manual Color/Size/Filter interactions, user screen layout "
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
