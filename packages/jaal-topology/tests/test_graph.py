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
