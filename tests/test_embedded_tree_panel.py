"""Stage 4 same-port embedding contracts (optional Dash deps)."""
import ast
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class EmbeddedTreePanelTests(unittest.TestCase):
    def setUp(self):
        try:
            from dash import Dash, no_update
            import dash_cytoscape
        except ImportError as exc:
            self.skipTest(f"Dash Cytoscape optional runtime not installed: {exc}")
        self.Dash = Dash
        self.no_update = no_update

    def test_initial_panel_is_empty_and_does_not_touch_graph_backend(self):
        from BertScript import embedded_tree_panel as panel
        with mock.patch.object(panel, "draw_graph", side_effect=AssertionError(
                "graph loaded without user action")):
            app = self.Dash(__name__)
            app.layout = panel.build_tree_panel()
            panel.register_tree_callbacks(app)

        def find(component, wanted):
            if getattr(component, "id", None) == wanted:
                return component
            for child in (getattr(component, "children", None) or []):
                if isinstance(child, (list, tuple)):
                    for part in child:
                        result = find(part, wanted)
                        if result is not None:
                            return result
                else:
                    result = find(child, wanted)
                    if result is not None:
                        return result
            return None

        graph = find(app.layout, "JaalGraph")
        self.assertIsNotNone(graph)
        self.assertEqual(graph.elements, [])
        self.assertFalse(find(app.layout, "JaalViewerCardDetails").open)
        self.assertEqual(find(app.layout, "JaalAllowFull").value, [])
        self.assertTrue(any("JaalGraph.elements" in k for k in app.callback_map))
        self.assertFalse(any(getattr(x, "src", "").endswith(":8053")
                             for x in app.layout.children if x is not None))

    def test_deny_full_without_consent_and_clear_without_io(self):
        from BertScript import embedded_tree_panel as panel
        with mock.patch.object(panel, "draw_graph", side_effect=AssertionError(
                "graph loaded without confirmation")):
            data = dict(root="A", depth=2, max_nodes=150, confirmed=[],
                        selected_node=None, previous_elements=[])
            refused = panel.render_action("btn_JaalViewerFull", **data)
            self.assertIs(refused[0], self.no_update)
            cleared = panel.render_action("btn_JaalViewerClear", **data)
            self.assertEqual(cleared[0], [])
            self.assertFalse(cleared[-1])

    def test_explicit_draw_and_manual_node_expansion(self):
        from BertScript import embedded_tree_panel as panel
        record = {"elements": [{"data": {"id": "A"}}], "nodes": 1,
                  "edges": 0, "total_nodes": 10, "total_edges": 9,
                  "truncated": False, "full": False}
        data = dict(root="A", depth=2, max_nodes=150, confirmed=[],
                    selected_node=None, previous_elements=[])
        with mock.patch.object(panel, "draw_graph", return_value=record) as call:
            output = panel.render_action("btn_JaalViewer", **data)
            self.assertEqual(output[0], record["elements"])
            call.assert_called_once_with(root="A", depth=2, max_nodes=150)
        with mock.patch.object(panel, "draw_graph", return_value=record) as call:
            data["selected_node"] = {"id": "A"}
            data["previous_elements"] = record["elements"]
            panel.render_action("btn_JaalViewerExpand", **data)
            call.assert_called_once_with(
                root="A", depth=2, max_nodes=150, existing_nodes=["A"])


class EmbeddedTreeSourceTests(unittest.TestCase):
    def test_stage_four_replaces_remote_iframe_without_jaal_server(self):
        source = (ROOT / "BertScript" / "Test_result_Vis.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        self.assertIn("register_tree_callbacks(app)", source)
        self.assertIn("build_tree_panel()", source)
        self.assertNotIn("http://{getIP()}:8053", source)
        self.assertNotIn("html.Iframe(", source)
        self.assertNotIn("Build_JaalViewCard", source)
        self.assertNotIn("JaalViewMain(", source)
        self.assertIn("dash-cytoscape", (ROOT / "requirements.txt").read_text(
            encoding="utf-8"))
        self.assertGreater(len(tree.body), 10)


if __name__ == "__main__":
    unittest.main()
