"""Tests that run without cloning text-category-profiler."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from jaal_topology import Graph, GraphInputError, load_graph, select_subgraph
from jaal_topology.modes import layout_options


class CSVInterfaceTests(unittest.TestCase):
    def test_examples_load_without_application_files(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        g = load_graph(examples / "relationships.csv",
                       examples / "metadata.csv")
        self.assertEqual(len(g.nodes), 5)
        self.assertEqual(len(g.edges), 5)
        self.assertEqual(g.translations["Technology"], "科技")
        self.assertEqual(
            select_subgraph(g, "Technology").nodes,
            ("AI", "Semiconductors", "Technology"),
        )
        self.assertEqual(g.edges[0], ("Root", "Technology"))

    def test_empty_translations_are_optional_and_ids_are_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edges.csv"
            path.write_text('parent,child\nA__B,C\nA,B__C\n',
                            encoding='utf-8')
            graph = load_graph(path)
            self.assertEqual(len(graph.edges), 2)
            self.assertEqual(graph.translations, {})
            with self.assertRaises(GraphInputError):
                select_subgraph(graph, max_nodes=1)


    def test_html_escapes_hover_only_not_literal_identifier(self):
        from jaal_topology.viewer import build_app
        unsafe = '<svg onload="alert(1)">'
        app = build_app(Graph((("Parent", unsafe),), ("Parent", unsafe), {}))
        def find(item):
            if isinstance(item, dict):
                if item.get("props", {}).get("id") == "graph":
                    return item["props"]["data"]["nodes"]
                for v in item.values():
                    found = find(v)
                    if found is not None:
                        return found
            elif isinstance(item, list):
                for v in item:
                    found = find(v)
                    if found is not None:
                        return found
            return None
        nodes = find(app.server.test_client().get("/_dash-layout").get_json())
        node = next(n for n in nodes if n["id"] == unsafe)
        self.assertEqual(node["label"], unsafe)
        self.assertIn("&lt;svg", node["title"])
        self.assertNotIn("<svg", node["title"])

    def test_wsgi_mount_keeps_host_and_assets_on_same_port(self):
        from flask import Flask
        from jaal_topology.integration import mount_flask

        examples = Path(__file__).resolve().parents[1] / "examples"
        graph = select_subgraph(
            load_graph(examples / "relationships.csv",
                       examples / "metadata.csv"), "Technology"
        )
        host = Flask(__name__)
        @host.route("/")
        def root():
            return "host-still-alive"
        child = mount_flask(
            host, graph, mount_path="/topology", root="Technology"
        )
        client = host.test_client()
        self.assertEqual(client.get("/").get_data(as_text=True),
                         "host-still-alive")
        result = client.get("/topology/")
        self.assertEqual(result.status_code, 200)
        self.assertIn("/topology/assets/16.jaal_visible_labels.js",
                      result.get_data(as_text=True))
        self.assertEqual(client.get("/topology/_dash-layout").status_code, 200)
        self.assertEqual(
            client.get("/topology/assets/17.jaal_structural_collapse.js").status_code,
            200,
        )
        self.assertEqual(
            client.get("/topology/assets/bootstrap.min.css").status_code, 200
        )
        with self.assertRaisesRegex(GraphInputError, "already mounted"):
            mount_flask(host, graph, mount_path="/topology")
        self.assertIsNotNone(child)

    def test_all_four_options_have_bounded_reversible_styles(self):
        base = {"nodes": {"shape": "dot"},
                "physics": {"enabled": True},
                "edges": {"smooth": {"enabled": True, "type": "dynamic"}}}
        for mode in ("network", "hierarchical",
                     "network-collapsed", "hierarchical-collapsed"):
            result = layout_options(base, mode)
            self.assertIsInstance(result, dict)
            self.assertIn("physics", result)
            self.assertEqual(base["nodes"]["shape"], "dot")
        hierarchical = layout_options(base, "hierarchical-collapsed")
        self.assertTrue(hierarchical["layout"]["hierarchical"]["enabled"])
        network = layout_options(base, "network")
        self.assertFalse(network["layout"]["hierarchical"]["enabled"])
