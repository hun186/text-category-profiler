"""Portable Jaal package tests: real CSV/WSGI, no Stage 4 activation."""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "packages" / "jaal-topology"
sys.path.insert(0, str(PACKAGE_ROOT))

from jaal_topology import GraphInputError, load_graph, select_subgraph  # noqa: E402
from jaal_topology.cli import parse_args, main  # noqa: E402


class PortableDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)

    def write(self, name, value):
        path = self.base / name
        path.write_text(value, encoding="utf-8-sig", newline="")
        return path

    def test_headed_three_column_edges_dag_and_optional_metadata(self):
        csv_path = self.write("edges.csv",
            "parent,child,relation\n"
            "Root,A,contains\nRoot,B,contains\n"
            "A,C,contains\nB,C,contains\nRoot,A,contains\n")
        meta = self.write("labels.csv",
            "ClassLabel,CT,Explanation,Notes\n"
            "Root,根類別,,\n"
            "A,   ,,\n"
            "B,中文乙,,\n"
            "Not in graph,不要傳輸,,\n")
        original = csv_path.read_bytes(), meta.read_bytes()
        graph = load_graph(csv_path, meta)
        self.assertEqual(graph.edges,
            (("Root", "A"), ("Root", "B"), ("A", "C"), ("B", "C")))
        self.assertEqual(graph.nodes, ("A", "B", "C", "Root"))
        self.assertEqual(graph.translations, {"Root": "根類別", "B": "中文乙"})
        subtree = select_subgraph(graph, "A")
        self.assertEqual(subtree.nodes, ("A", "C"))
        self.assertEqual(subtree.edges, (("A", "C"),))
        self.assertEqual(subtree.translations, {})
        self.assertEqual((csv_path.read_bytes(), meta.read_bytes()), original)

    def test_headerless_repeated_edges_and_cycle_are_not_rewritten(self):
        a = self.write("one.csv", "Root,A\nA,Root\n")
        b = self.write("two.csv", "Root,A\nX,Y\n")
        graph = load_graph([a, b])
        self.assertEqual(graph.edges,
            (("Root", "A"), ("A", "Root"), ("X", "Y")))
        self.assertEqual(select_subgraph(graph, "Root").nodes, ("A", "Root"))
        self.assertEqual(select_subgraph(graph, "X").nodes, ("X", "Y"))
        self.assertEqual(select_subgraph(graph).nodes, ("A", "Root", "X", "Y"))

    def test_alternative_schema_and_blank_translation(self):
        edges = self.write("edges.csv", "#母類別,子類別\n根,枝\n")
        meta = self.write("meta.csv", "id,text\n根,中文根\n枝,\n")
        graph = load_graph(edges, meta, metadata_id_column="id",
                           metadata_label_column="text")
        self.assertEqual(graph.nodes, ("枝", "根"))
        self.assertEqual(graph.translations, {"根": "中文根"})

    def test_bounded_graph_and_root_validation(self):
        graph = load_graph(self.write("edges.csv",
            "source,target\nA,B\nB,C\nC,A\nB,D\n"))
        with self.assertRaisesRegex(GraphInputError, "exceeds"):
            select_subgraph(graph, max_nodes=2)
        with self.assertRaisesRegex(GraphInputError, "exceeds"):
            select_subgraph(graph, "A", max_nodes=3)
        with self.assertRaisesRegex(GraphInputError, "edges"):
            select_subgraph(graph, "A", max_edges=2)
        with self.assertRaisesRegex(GraphInputError, "Unknown graph root"):
            select_subgraph(graph, "NotFound")
        with self.assertRaises(GraphInputError):
            select_subgraph(graph, max_nodes=True)
        with self.assertRaises(GraphInputError):
            select_subgraph(graph, max_edges=5001)

    def test_malformed_csv_and_duplicate_metadata_are_explicit_errors(self):
        with self.assertRaisesRegex(GraphInputError, "two edge columns"):
            load_graph(self.write("bad.csv", "A\n"))
        with self.assertRaisesRegex(GraphInputError, "blank edge endpoint"):
            load_graph(self.write("blank.csv", "A,\n"))
        edges = self.write("good.csv", "A,B\n")
        badmeta = self.write("duplicate.csv",
            "ClassLabel,CT\nA,甲\nA,乙\n")
        with self.assertRaisesRegex(GraphInputError, "duplicate metadata"):
            load_graph(edges, badmeta)
        with self.assertRaisesRegex(GraphInputError, "metadata needs"):
            load_graph(edges, self.write("wrong.csv", "bad,headers\nA,甲\n"))

    def test_cli_help_and_validation_is_model_workpool_free(self):
        other = self.base / "external-project"
        other.mkdir()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PACKAGE_ROOT)
        proc = subprocess.run([sys.executable, "-m", "jaal_topology", "--help"],
                              cwd=other, env=env, capture_output=True,
                              text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--metadata-id-column", proc.stdout)
        self.assertIn("--max-nodes", proc.stdout)
        self.assertIn("--edges", proc.stdout)
        self.assertEqual(parse_args(["--edges", "x.csv"]).port, 8059)
        with self.assertRaises(SystemExit):
            parse_args(["--edges", "x.csv", "--port", "0"])
        self.assertEqual(main(["--edges", str(other / "missing.csv")]), 2)

    def test_pure_data_import_has_no_runtime_application_dependencies(self):
        import jaal_topology.data as data
        self.assertNotIn("BertScript", data.__dict__)
        self.assertNotIn("ClassesTree", data.__dict__)
        self.assertNotIn("jaal", data.__dict__)
        self.assertNotIn("dash", data.__dict__)


class PortableRealJaalTests(unittest.TestCase):
    def setUp(self):
        try:
            import dash
            import jaal
            import pandas
            import visdcc
        except ImportError as exc:
            self.skipTest(f"Standalone optional Jaal runtime unavailable: {exc}")

    def test_adapted_dataframe_contains_directed_edges_and_searchable_ids(self):
        from jaal_topology.data import Graph
        from jaal_topology.viewer import to_jaal_dataframes, _search_english_id
        graph = Graph((("A", "B"), ("C", "B")), ("A", "B", "C"),
                      {"B": "節點乙"})
        edges, nodes = to_jaal_dataframes(graph)
        self.assertEqual(list(edges[["from", "to"]].itertuples(
            index=False, name=None)), [("A", "B"), ("C", "B")])
        self.assertEqual(nodes.loc[nodes["id"] == "B", "InDegree"].item(), 2)
        self.assertEqual(nodes.loc[nodes["id"] == "B", "Degree"].item(), 2)
        items = {"nodes": [{"id": "B", "label": "節點乙"},
                           {"id": "C", "label": "C"}], "edges": []}
        _search_english_id(items, "B")
        self.assertFalse(items["nodes"][0]["hidden"])
        self.assertTrue(items["nodes"][1]["hidden"])
        self.assertEqual(items["nodes"][0]["label"], "節點乙")

    def test_standalone_real_jaal_dash_layout_and_callbacks(self):
        from jaal_topology.data import Graph
        from jaal_topology.viewer import build_app
        graph = Graph((("Root", "Branch"), ("Branch", "Leaf")),
                      ("Branch", "Leaf", "Root"), {"Branch": "分支"})
        app = build_app(graph, root="Root")
        c = app.server.test_client()
        layout = c.get("/_dash-layout")
        self.assertEqual(layout.status_code, 200, layout.data[:400])
        payload = layout.get_json()
        found = {}
        def walk(node):
            if isinstance(node, dict):
                props = node.get("props", {})
                if "id" in props:
                    found[props["id"]] = props
                for part in node.values():
                    walk(part)
            elif isinstance(node, list):
                for child in node:
                    walk(child)
        walk(payload)
        for key in ("graph", "topology-chinese", "topology-mode",
                    "topology-translations", "topology-physics-restore",
                    "search_graph", "filter_node"):
            if key == "filter_node":
                continue  # upstream uses dynamic field names
            self.assertIn(key, found)
        self.assertEqual(found["topology-chinese"]["value"], [])
        self.assertEqual(found["topology-mode"]["value"], "network")
        self.assertEqual(found["topology-translations"]["data"],
                         {"Branch": "分支"})
        nodes = found["graph"]["data"]["nodes"]
        self.assertEqual({node["id"] for node in nodes},
                         {"Branch", "Leaf", "Root"})
        self.assertTrue(all(node.get("title", node["id"]) == node["id"]
                            for node in nodes))
        deps = c.get("/_dash-dependencies").get_json()
        label = [item for item in deps if item["output"] == "graph.run"]
        self.assertEqual(len(label), 1)
        self.assertTrue(label[0]["clientside_function"])
        self.assertEqual({i["id"] for i in label[0]["inputs"]},
                         {"topology-chinese", "topology-translations", "graph"})
        self.assertTrue(any("graph.options" in d["output"] for d in deps))
        self.assertTrue(any("graph.data" in d["output"] and
                            any(x["id"] == "search_graph" for x in d["inputs"])
                            for d in deps))
        # One real, original Jaal instance; no adjacent application imports.
        self.assertNotIn("WorkPool", str(payload))
