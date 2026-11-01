"""Original Jaal preserved under same-port WSGI, with explicit lazy activation."""
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class OriginalJaalMountTests(unittest.TestCase):
    def setUp(self):
        try:
            import dash
            import jaal
            import pandas
            import flask
            import werkzeug
            import dash_bootstrap_components
        except ImportError as exc:
            self.skipTest(f"Optional original Jaal integration dependencies absent: {exc}")

    def test_main_page_draws_no_jaal_app_or_iframe(self):
        from BertScript import jaal_original_panel as panel
        from dash import Dash
        with mock.patch.object(panel.router, "_build_app",
                               side_effect=AssertionError("Jaal eagerly built")):
            app = Dash(__name__)
            result = panel.build_original_jaal_panel()
            app.layout = result
        rendered = str(result)
        self.assertIn("原版 Jaal 進階檢視器", rendered)
        self.assertIn("JaalOriginalRoot", rendered)
        self.assertIn("JaalOriginalLargeConsent", rendered)
        self.assertIn("JaalOriginalFrame", rendered)
        self.assertNotIn("Iframe(", rendered)
        self.assertNotIn("src='http://", rendered)
        self.assertNotIn("src=\"http://", rendered)

    def test_lazy_same_port_wsgimount_with_dynamic_callback_paths(self):
        from flask import Flask
        from werkzeug.test import Client
        from werkzeug.wrappers import Response
        from BertScript.jaal_original_mount import OriginalJaalRouter
        from jaal import Jaal
        import pandas as pd

        server = Flask(__name__)

        @server.route("/")
        def hello():
            return "main-dash-still-alive"

        created = []

        def make_small_original_app(root, prefix):
            created.append((root, prefix))
            edges = pd.DataFrame([("A", "B"), ("B", "C")],
                                 columns=["from", "to"])
            nodes = pd.DataFrame([("A", 1), ("B", 2), ("C", 3)],
                                 columns=["id", "depth"])
            from BertScript.jaal_original_mount import prefix_original_jaal
            app = Jaal(edges, nodes).create(directed=True,
                                            vis_opts={"height": "600px"})
            return prefix_original_jaal(app, prefix)

        router = OriginalJaalRouter(build_app=make_small_original_app)
        router.mount(server)
        router.mount(server)
        with mock.patch(
            "BertScript.jaal_original_mount.subtree_stats",
            return_value={"root": "A", "nodes": 3, "edges": 2},
        ):
            url, stats = router.prepare("A")
        self.assertEqual(len(created), 0, "must not create Jaal on prepare")
        self.assertEqual(stats["nodes"], 3)
        client = Client(server.wsgi_app, Response)
        self.assertEqual(client.get("/").data, b"main-dash-still-alive")
        self.assertEqual(client.get("/jaal-original/not-registered/").status_code, 404)
        response = client.get(url)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:250])
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0], ("A", url))
        self.assertIn(url, response.get_data(as_text=True),
                      "Dash resource prefixes must remain same-origin and mounted")
        # The child app serves its own bounded, same-origin auto-height script;
        # no external CDN, graph rebuild, or second port is involved.
        size_js = url + "assets/15.jaal_embedded_autoheight.js"
        self.assertIn(size_js, response.get_data(as_text=True))
        size_response = client.get(size_js)
        self.assertEqual(size_response.status_code, 200)
        script = size_response.get_data(as_text=True)
        self.assertIn('getElementById("jaal-original-content")', script)
        self.assertIn('classList.contains("jaal-original-iframe")', script)
        self.assertIn("ResizeObserver", script)
        self.assertIn("1600", script)
        self.assertNotIn("network.fit(", script)
        # The iframe must not rely exclusively on a remotely hosted Bootstrap
        # stylesheet. Without its 25/75% grid, Jaal's UI and graph spill out.
        local_css = url + "assets/bootstrap@5.3.1/bootstrap.min.css"
        self.assertIn(local_css, response.get_data(as_text=True))
        css_response = client.get(local_css)
        self.assertEqual(css_response.status_code, 200)
        self.assertIn(b".row{", css_response.data)
        self.assertIn(b".col-9{", css_response.data)
        layout = client.get(url + "_dash-layout")
        callbacks = client.get(url + "_dash-dependencies")
        self.assertEqual(layout.status_code, 200, layout.get_data(as_text=True)[:300])
        self.assertEqual(callbacks.status_code, 200, callbacks.get_data(as_text=True)[:300])
        tree = json.loads(layout.get_data(as_text=True))
        elements = []

        def collect(item):
            if isinstance(item, dict):
                if "props" in item:
                    elements.append(item)
                for child in item.values():
                    collect(child)
            elif isinstance(item, list):
                for child in item:
                    collect(child)

        collect(tree)
        logo = [
            item["props"] for item in elements
            if item.get("type") == "Img"
            and str(item["props"].get("src", "")).startswith("data:image/png;base64,")
        ]
        self.assertEqual(len(logo), 1)
        self.assertEqual(logo[0]["width"], 80)
        self.assertEqual(logo[0]["style"]["width"], "80px")
        self.assertEqual(logo[0]["style"]["height"], "auto")
        network = [
            item["props"] for item in elements
            if item["props"].get("id") == "graph"
        ]
        self.assertEqual(len(network), 1)
        self.assertEqual(network[0]["options"]["height"], "600px")
        components_by_id = {
            item["props"]["id"]: item for item in elements
            if isinstance(item["props"].get("id"), str)
        }
        self.assertIn("jaal-original-content", components_by_id)
        self.assertEqual(components_by_id["jaal-original-content"]["type"], "Div")
        sidebar = components_by_id["jaal-original-settings-column"]
        graph_column = components_by_id["jaal-original-graph-column"]
        toggle = components_by_id["jaal-original-sidebar-toggle"]
        self.assertEqual(sidebar["props"]["width"], 3)
        # Upstream Jaal vertically centers the shorter settings card; the
        # embedded view must start at row top even when sections are hidden.
        self.assertEqual(sidebar["props"]["style"]["align-items"], "flex-start")
        self.assertEqual(graph_column["props"]["width"], 9)
        self.assertIn("收合左側設定", toggle["props"]["children"])
        self.assertEqual(toggle["props"]["n_clicks"], 0)
        self.assertIn("aria-label", toggle["props"])
        # The toggle stays in the graph column even when sidebar is hidden.
        self.assertIn("jaal-original-sidebar-toggle", json.dumps(graph_column,
                          ensure_ascii=False))
        self.assertNotIn("jaal-original-sidebar-toggle", json.dumps(sidebar,
                          ensure_ascii=False))
        serialized = callbacks.get_data(as_text=True)
        dependencies = json.loads(serialized)
        sidebar_callback = [
            dep for dep in dependencies
            if "jaal-original-settings-column.style" in dep["output"]
            and "jaal-original-graph-column.width" in dep["output"]
        ]
        self.assertEqual(len(sidebar_callback), 1)
        self.assertTrue(any("jaal-original-sidebar-toggle" in str(dep)
                            for dep in dependencies))
        self.assertTrue(any(
            dep["output"] == "jaal-original-sidebar-toggle.title"
            for dep in dependencies
        ))
        self.assertFalse(any(
            "graph.data" in dep["output"] and
            "jaal-original-sidebar-toggle" in str(dep)
            for dep in dependencies
        ))
        # Exercise the *real* mounted Dash multi-output HTTP callback; a
        # collapsed panel should give the graph all 12 Bootstrap columns.
        for clicks, expected_width, expected_display, expected_text in (
            (1, 12, "none", "展開左側設定"),
            (2, 9, "flex", "收合左側設定"),
        ):
            result = client.post(
                url + "_dash-update-component",
                json={
                    "output": sidebar_callback[0]["output"],
                    "outputs": [
                        {"id": "jaal-original-settings-column", "property": "style"},
                        {"id": "jaal-original-graph-column", "property": "width"},
                        {"id": "jaal-original-sidebar-toggle", "property": "children"},
                    ],
                    "inputs": [{"id": "jaal-original-sidebar-toggle",
                                "property": "n_clicks", "value": clicks}],
                    "state": [],
                    "changedPropIds": ["jaal-original-sidebar-toggle.n_clicks"],
                },
            )
            self.assertEqual(result.status_code, 200,
                             result.get_data(as_text=True)[:400])
            changed = result.get_json()["response"]
            self.assertEqual(changed["jaal-original-settings-column"]["style"]["display"],
                             expected_display)
            if expected_display == "flex":
                self.assertEqual(
                    changed["jaal-original-settings-column"]["style"]["alignItems"],
                    "flex-start",
                )
            self.assertEqual(changed["jaal-original-graph-column"]["width"],
                             expected_width)
            self.assertIn(expected_text,
                          changed["jaal-original-sidebar-toggle"]["children"])
        self.assertEqual(len(created), 1, "toggle must reuse mounted Jaal")
        # Graph data and all original user settings remain in the same tree.
        self.assertEqual(
            json.loads(client.get(url + "_dash-layout").get_data(as_text=True)),
            tree,
        )
        for original_control in ("search_graph", "filter_nodes", "filter_edges",
                                 "color_nodes", "color_edges",
                                 "size_nodes", "size_edges"):
            self.assertIn(original_control, serialized)
        self.assertEqual(len(created), 1, "reuse one mounted app within same root")

    def test_iframe_fallback_is_bounded_when_javascript_is_disabled(self):
        from BertScript.jaal_original_panel import build_original_jaal_iframe
        frame = build_original_jaal_iframe("/jaal-original/test/")
        self.assertEqual(frame.src, "/jaal-original/test/")
        self.assertEqual(frame.className, "jaal-original-iframe")
        self.assertEqual(frame.style["height"], "800px")
        self.assertNotEqual(frame.style["height"], "1100px")
        self.assertEqual(frame.style["width"], "100%")
        self.assertEqual(frame.style["display"], "block")
        self.assertNotIn("overflow", frame.style)

    def test_sidebar_geometry_only_changes_visibility_and_bootstrap_width(self):
        from BertScript.jaal_original_mount import _sidebar_toggle_geometry
        expanded = _sidebar_toggle_geometry(0)
        collapsed = _sidebar_toggle_geometry(1)
        reopened = _sidebar_toggle_geometry(2)
        self.assertEqual(expanded[1], 9)
        self.assertEqual(collapsed[0]["display"], "none")
        self.assertEqual(collapsed[1], 12)
        self.assertEqual(reopened[0]["display"], "flex")
        self.assertEqual(expanded[0]["alignItems"], "flex-start")
        self.assertEqual(reopened[0]["alignItems"], "flex-start")
        self.assertEqual(reopened[1], 9)
        self.assertEqual(reopened, expanded)

    def test_logo_normalization_does_not_rewrite_other_images(self):
        from dash import html
        from BertScript.jaal_original_mount import _normalize_original_jaal_logo
        photo = html.Img(src="https://example.org/photo.png", width=800)
        newer_logo = html.Img(src="data:image/png;base64,AAAA", width=80)
        legacy_logo = html.Img(src="data:image/png;base64,BBBB", width="80px")
        tree = html.Div([photo, html.Div([newer_logo, legacy_logo])])
        self.assertTrue(_normalize_original_jaal_logo(tree))
        self.assertEqual(legacy_logo.width, 80)
        self.assertEqual(legacy_logo.style["width"], "80px")
        self.assertEqual(photo.width, 800)
        self.assertEqual(newer_logo.width, 80)
        self.assertFalse(_normalize_original_jaal_logo(tree))

    def test_ordinary_large_and_absolute_resource_limits(self):
        from BertScript.jaal_original_mount import OriginalJaalRouter
        router = OriginalJaalRouter(build_app=mock.Mock())
        with mock.patch("BertScript.jaal_original_mount.subtree_stats",
                        return_value={"root": "A", "nodes": 459, "edges": 534}):
            with self.assertRaisesRegex(ValueError, "勾選"):
                router.prepare("A")
            url, _ = router.prepare("A", confirmed_large=True)
            self.assertTrue(url.startswith("/jaal-original/"))
            self.assertEqual(router._apps, {}, "no expensive Jaal instance on prepare")
        with mock.patch("BertScript.jaal_original_mount.subtree_stats",
                        return_value={"root": "X", "nodes": 3001, "edges": 4000}):
            with self.assertRaisesRegex(ValueError, "安全上限"):
                router.prepare("X", confirmed_large=True)
        with mock.patch("BertScript.jaal_original_mount.subtree_stats",
                        return_value={"root": "X", "nodes": 2600, "edges": 5001}):
            with self.assertRaisesRegex(ValueError, "安全上限"):
                router.prepare("X", confirmed_large=True)

    def test_real_taxonomy_preflight_counts_and_untrusted_roots(self):
        from BertScript.jaal_original_mount import subtree_stats
        tw = subtree_stats("TW Affairs")
        self.assertGreater(tw["nodes"], 20)
        self.assertLess(tw["nodes"], 250)
        self.assertGreater(tw["edges"], 20)
        self.assertGreater(subtree_stats("Spacetime Singularity Of Tree")["nodes"], 2000)
        with self.assertRaisesRegex(ValueError, "ClassLabel"):
            subtree_stats('TW Affairs"); __import__("os")')


class OriginalJaalSourceContractTests(unittest.TestCase):
    def test_preserves_standalone_jaal_and_both_stage4_panels(self):
        jaal = (ROOT / "ClassesTree" / "Visualization" / "jaal" / "jaalViewer.py"
                ).read_text(encoding="utf-8")
        entry = (ROOT / "BertScript" / "Test_result_Vis.py").read_text(
            encoding="utf-8")
        self.assertIn("JaalViewMain(", jaal)
        self.assertIn("Jaal(edge_df, node_df).plot(", jaal)
        self.assertIn("Jaal(edge_df, node_df).create(", jaal)
        # Jaal.create() cannot take host=; original .plot() can.
        create = jaal.split("if createMode == True:", 1)[1].split("else:", 1)[0]
        self.assertNotIn("host = hostIP", create)
        self.assertIn('str.contains(f"#T#{QueryRoot}#T#", regex=False', jaal)
        self.assertIn("build_tree_panel(),", entry)
        self.assertIn("build_original_jaal_panel(),", entry)
        self.assertIn("register_original_jaal(app)", entry)
        self.assertIn("jaal  # Original visdcc", (
            ROOT / "requirements.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
