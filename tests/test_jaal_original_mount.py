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
        self.assertIn("Jaal 進階檢視器", rendered)
        self.assertIn("載入 Jaal", rendered)
        self.assertNotIn("原版 Jaal", rendered)
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
            edges = pd.DataFrame([("A", "CN Intelligence And Espionage Against TW"),
                                  ("CN Intelligence And Espionage Against TW", "TW Affairs")],
                                 columns=["from", "to"])
            nodes = pd.DataFrame([
                ("A", 1), ("CN Intelligence And Espionage Against TW", 2),
                ("TW Affairs", 3),
            ], columns=["id", "depth"])
            from ClassesTree.Visualization.jaal.label_format import wrapped_classlabel
            nodes["label"] = nodes["id"].map(wrapped_classlabel)
            nodes["title"] = nodes["id"]
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
        self.assertNotIn("hierarchical", network[0]["options"].get("layout", {}))
        # Real Jaal/visdcc must preserve explicit newline-bearing display
        # labels in the HTTP Dash layout, not merely advertise options.
        node_payload = network[0]["data"]["nodes"]
        long_node = next(item for item in node_payload if item["id"] ==
                         "CN Intelligence And Espionage Against TW")
        self.assertIn(chr(10), long_node["label"])
        self.assertEqual(long_node["title"], long_node["id"])
        self.assertEqual(long_node["id"], "CN Intelligence And Espionage Against TW")
        self.assertTrue(any(item["id"] == "TW Affairs" and
                            item["label"] == "TW Affairs" for item in node_payload))
        components_by_id = {
            item["props"]["id"]: item for item in elements
            if isinstance(item["props"].get("id"), str)
        }
        self.assertIn("jaal-original-content", components_by_id)
        self.assertEqual(components_by_id["jaal-original-content"]["type"], "Div")
        # Upstream Jaal's two top-level dbc.Rows are not inside a Bootstrap
        # .container. Standard negative row gutters overflow the iframe by
        # a few pixels, triggering a horizontal *and then* vertical scrollbar.
        # g-0 fixes geometry, rather than clipping true overflow.
        jaal_root = components_by_id["jaal-original-content"]["props"]["children"]
        self.assertEqual(jaal_root["type"], "Div")
        outer_rows = jaal_root["props"]["children"]
        self.assertEqual(len(outer_rows), 2)
        for row in outer_rows:
            self.assertEqual(row["type"], "Row")
            self.assertIn("g-0", row["props"]["className"].split())
        # Bootstrap minifies these as grouped selectors, not ".g-0{".
        # Both horizontal and vertical gutter variables must be zero.
        self.assertIn(b".g-0,.gx-0{--bs-gutter-x:0", css_response.data)
        self.assertIn(b".g-0,.gy-0{--bs-gutter-y:0", css_response.data)
        sidebar = components_by_id["jaal-original-settings-column"]
        graph_column = components_by_id["jaal-original-graph-column"]
        toggle = components_by_id["jaal-original-sidebar-toggle"]
        mode = components_by_id["jaal-original-layout-mode"]["props"]
        self.assertEqual(mode["value"], "network")
        restore_timer = components_by_id["jaal-original-physics-restore"]["props"]
        self.assertTrue(restore_timer["disabled"])
        self.assertEqual(restore_timer["interval"], 300)
        self.assertEqual(mode["options"], [
            {"label": "網狀", "value": "network"},
            {"label": "階層樹狀", "value": "hierarchical"},
        ])
        self.assertIn("jaal-original-layout-mode",
                      json.dumps(graph_column, ensure_ascii=False))
        self.assertIn("jaal-original-hierarchy-hint",
                      json.dumps(graph_column, ensure_ascii=False))
        self.assertNotIn("jaal-original-layout-mode",
                         json.dumps(sidebar, ensure_ascii=False))
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
        # The new options callback must not compete with Jaal's existing
        # Search/Filter/Color/Size callback for graph.data.
        graph_option_callbacks = [
            dep for dep in dependencies
            if "graph.options" in dep["output"]
            and "jaal-original-physics-restore.disabled" in dep["output"]
        ]
        self.assertEqual(len(graph_option_callbacks), 1)
        self.assertTrue(any(
            item["id"] == "jaal-original-layout-mode"
            and item["property"] == "value"
            for item in graph_option_callbacks[0]["inputs"]
        ))
        self.assertTrue(any("graph.data" in dep["output"]
                            for dep in dependencies))
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
        baseline_options = network[0]["options"]
        for choice in ("hierarchical", "network"):
            result = client.post(
                url + "_dash-update-component",
                json={
                    "output": graph_option_callbacks[0]["output"],
                    "outputs": [
                        {"id": "graph", "property": "options"},
                        {"id": "jaal-original-physics-restore",
                         "property": "disabled"},
                    ],
                    "inputs": [
                        {"id": "jaal-original-layout-mode",
                         "property": "value", "value": choice},
                        {"id": "jaal-original-physics-restore",
                         "property": "n_intervals", "value": 0},
                    ],
                    "state": [],
                    "changedPropIds": ["jaal-original-layout-mode.value"],
                },
            )
            self.assertEqual(result.status_code, 200,
                             result.get_data(as_text=True)[:450])
            changed_mode = result.get_json()["response"]
            self.assertEqual(
                changed_mode["jaal-original-physics-restore"]["disabled"],
                choice == "hierarchical",
            )
            options = changed_mode["graph"]["options"]
            if choice == "hierarchical":
                self.assertEqual(options["layout"]["hierarchical"]["direction"], "UD")
                self.assertEqual(options["layout"]["hierarchical"]["sortMethod"],
                                 "directed")
                self.assertEqual(options["layout"]["hierarchical"]["nodeSpacing"], 245)
                self.assertEqual(options["layout"]["hierarchical"]["treeSpacing"], 310)
                self.assertEqual(options["layout"]["hierarchical"]["levelSeparation"], 205)
                self.assertEqual(options["nodes"]["widthConstraint"], {"maximum": 145})
                self.assertFalse(options["physics"]["enabled"])
                self.assertTrue(options["edges"]["arrows"]["to"])
                self.assertEqual(options["height"], "600px")
            else:
                self.assertFalse(options["layout"]["hierarchical"]["enabled"])
                self.assertFalse(options["nodes"]["widthConstraint"])
                self.assertTrue(options["physics"]["enabled"])
                self.assertEqual(options["physics"]["stabilization"],
                                 baseline_options["physics"]["stabilization"])
                self.assertEqual(options["edges"]["smooth"]["type"], "dynamic")
                self.assertEqual(options["edges"]["smooth"]["forceDirection"], "none")
                self.assertEqual(options["edges"]["arrows"],
                                 baseline_options["edges"]["arrows"])
                self.assertEqual(options["height"], baseline_options["height"])
                self.assertEqual(options["interaction"], baseline_options["interaction"])
        # The vis.js layout engine may restore physics=false from its own
        # hierarchy backup AFTER the first setOptions() call. The timer sends
        # a separate second update to restore physics after that transition.
        tick = client.post(
            url + "_dash-update-component",
            json={
                "output": graph_option_callbacks[0]["output"],
                "outputs": [
                    {"id": "graph", "property": "options"},
                    {"id": "jaal-original-physics-restore", "property": "disabled"},
                ],
                "inputs": [
                    {"id": "jaal-original-layout-mode",
                     "property": "value", "value": "network"},
                    {"id": "jaal-original-physics-restore",
                     "property": "n_intervals", "value": 1},
                ],
                "state": [],
                "changedPropIds": ["jaal-original-physics-restore.n_intervals"],
            },
        )
        self.assertEqual(tick.status_code, 200,
                         tick.get_data(as_text=True)[:450])
        ticks = tick.get_json()["response"]
        restored_options = ticks["graph"]["options"]
        self.assertTrue(restored_options["physics"]["enabled"])
        self.assertEqual(restored_options["edges"]["smooth"]["type"], "dynamic")
        self.assertEqual(restored_options["edges"]["smooth"]["forceDirection"], "none")
        self.assertEqual(restored_options["edges"]["smooth"]["roundness"], 0.5)
        self.assertTrue(ticks["jaal-original-physics-restore"]["disabled"])
        self.assertFalse(restored_options["nodes"]["widthConstraint"])
        # Racing mode changes cannot re-enable physics in hierarchy mode.
        raced = client.post(
            url + "_dash-update-component",
            json={
                "output": graph_option_callbacks[0]["output"],
                "outputs": [
                    {"id": "graph", "property": "options"},
                    {"id": "jaal-original-physics-restore", "property": "disabled"},
                ],
                "inputs": [
                    {"id": "jaal-original-layout-mode",
                     "property": "value", "value": "hierarchical"},
                    {"id": "jaal-original-physics-restore",
                     "property": "n_intervals", "value": 2},
                ],
                "state": [],
                "changedPropIds": ["jaal-original-physics-restore.n_intervals"],
            },
        )
        self.assertEqual(raced.status_code, 200)
        self.assertNotIn("graph", raced.get_json()["response"])
        self.assertTrue(
            raced.get_json()["response"]["jaal-original-physics-restore"]["disabled"]
        )
        self.assertEqual(len(created), 1, "mode toggle must reuse mounted Jaal")
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

    def test_hierarchical_mode_is_reversible_and_preserves_original_options(self):
        from BertScript.jaal_original_mount import _jaal_layout_options
        original = {
            "height": "600px", "width": "100%",
            "interaction": {"hover": True},
            "physics": {"stabilization": {"iterations": 100}},
            "edges": {"arrows": {"to": True}, "width": 2},
            "nodes": {"font": {"size": 15}},
        }
        import copy
        snapshot = copy.deepcopy(original)
        tree = _jaal_layout_options(original, "hierarchical")
        self.assertTrue(tree["layout"]["hierarchical"]["enabled"])
        self.assertEqual(tree["layout"]["hierarchical"]["direction"], "UD")
        self.assertEqual(tree["layout"]["hierarchical"]["sortMethod"], "directed")
        self.assertFalse(tree["physics"]["enabled"])
        self.assertEqual(tree["edges"]["smooth"]["type"], "cubicBezier")
        self.assertEqual(tree["nodes"]["font"], original["nodes"]["font"])
        self.assertEqual(tree["nodes"]["widthConstraint"], {"maximum": 145})
        self.assertEqual(tree["layout"]["hierarchical"]["nodeSpacing"], 245)
        self.assertEqual(tree["layout"]["hierarchical"]["treeSpacing"], 310)
        self.assertEqual(tree["edges"]["arrows"], original["edges"]["arrows"])
        reset = _jaal_layout_options(original, "network")
        self.assertFalse(reset["layout"]["hierarchical"]["enabled"])
        self.assertTrue(reset["physics"]["enabled"])
        self.assertEqual(reset["physics"]["stabilization"],
                         snapshot["physics"]["stabilization"])
        self.assertEqual(reset["edges"]["smooth"]["type"], "dynamic")
        for field in ("height", "width", "interaction"):
            self.assertEqual(reset[field], snapshot[field])
        self.assertEqual(reset["nodes"]["font"], snapshot["nodes"]["font"])
        self.assertFalse(reset["nodes"]["widthConstraint"])
        self.assertEqual(reset["edges"]["arrows"], snapshot["edges"]["arrows"])
        self.assertEqual(original, snapshot, "source settings must not be mutated")

        def merge_options(current, update):
            # Model vis-network setOptions()' recursive merge semantics.
            # An absent key is NOT cleared from the live network instance.
            result = copy.deepcopy(current)
            for key, value in update.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge_options(result[key], value)
                else:
                    result[key] = copy.deepcopy(value)
            return result

        effective_tree = merge_options(snapshot, tree)
        self.assertTrue(effective_tree["layout"]["hierarchical"]["enabled"])
        self.assertEqual(effective_tree["nodes"]["widthConstraint"], {"maximum": 145})
        self.assertFalse(effective_tree["physics"]["enabled"])
        effective_network = merge_options(effective_tree, reset)
        self.assertFalse(effective_network["layout"]["hierarchical"]["enabled"])
        self.assertFalse(effective_network["nodes"]["widthConstraint"])
        self.assertTrue(effective_network["physics"]["enabled"])
        self.assertEqual(effective_network["edges"]["smooth"]["type"], "dynamic")
        self.assertEqual(effective_network["edges"]["smooth"]["forceDirection"], "none")
        self.assertEqual(effective_network["edges"]["arrows"], snapshot["edges"]["arrows"])

        # LayoutEngine's exit-hierarchy backup can overwrite the stage-1
        # settings (physics to false and smooth to a bare boolean True).
        # That boolean changes only smooth.enabled in the vis.js parser,
        # leaving the tree's cubicBezier curve settings in place. Stage 2
        # must explicitly restore all affected options after the backup.
        after_engine_exit = copy.deepcopy(effective_network)
        after_engine_exit["physics"]["enabled"] = False
        after_engine_exit["edges"]["smooth"].update({
            "enabled": True, "type": "cubicBezier",
            "forceDirection": "vertical", "roundness": 0.28,
        })
        stage2 = {
            "physics": {"enabled": snapshot["physics"].get("enabled", True)},
            "edges": {"smooth": reset["edges"]["smooth"]},
            "nodes": {"widthConstraint": reset["nodes"]["widthConstraint"]},
        }
        final_state = merge_options(after_engine_exit, stage2)
        self.assertTrue(final_state["physics"]["enabled"])
        self.assertEqual(final_state["edges"]["smooth"]["type"], "dynamic")
        self.assertEqual(final_state["edges"]["smooth"]["forceDirection"], "none")
        self.assertEqual(final_state["edges"]["smooth"]["roundness"], 0.5)
        self.assertEqual(final_state["edges"]["arrows"], snapshot["edges"]["arrows"])
        self.assertFalse(final_state["nodes"]["widthConstraint"])
        # Respect an explicitly configured original width limit in network mode.
        custom = copy.deepcopy(original)
        custom["nodes"]["widthConstraint"] = {"maximum": 265}
        self.assertEqual(
            _jaal_layout_options(custom, "network")["nodes"]["widthConstraint"],
            {"maximum": 265},
        )
        self.assertEqual(custom["nodes"]["widthConstraint"], {"maximum": 265})
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            _jaal_layout_options(original, "invalid")

    def test_only_jaal_outer_rows_get_zero_gutters(self):
        from dash import html
        import dash_bootstrap_components as dbc
        from BertScript.jaal_original_mount import (
            _remove_embedded_jaal_outer_row_gutters,
        )
        nested = dbc.Row(html.Div("Preserved"), className="nested")
        logo = dbc.Row(html.Span("Logo"), className="column flex-display")
        graph = dbc.Row([dbc.Col(nested), dbc.Col(html.Div("Graph"))],
                        className="column flex-display")
        root = html.Div([logo, graph])
        _remove_embedded_jaal_outer_row_gutters(root)
        self.assertEqual(logo.className, "column flex-display g-0")
        self.assertEqual(graph.className, "column flex-display g-0")
        self.assertEqual(nested.className, "nested",
                         "nested Filter/Color layout must remain unchanged")
        _remove_embedded_jaal_outer_row_gutters(root)
        self.assertEqual(graph.className.count("g-0"), 1,
                         "normalizing twice must not stack CSS classes")
        with self.assertRaisesRegex(RuntimeError, "structure changed"):
            _remove_embedded_jaal_outer_row_gutters(html.Div([logo]))

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
        self.assertIn('node_df["label"] = node_df["id"].map(wrapped_classlabel)', jaal)
        self.assertIn('node_df["title"] = node_df["id"]', jaal)
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
