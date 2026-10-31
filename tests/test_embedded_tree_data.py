"""Real taxonomy and synthetic bounded-graph acceptance without a Dash server."""
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ClassesTree.Visualization.embedded_tree import (
    DATA_DIR, TOPIC_FILES, DEFAULT_MAX_NODES, MAX_FULL_NODES,
    GraphLimitError, draw_graph, load_graph,
)


class EmbeddedTreeDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "TopicTree.csv"

    def write_edges(self, edges):
        with self.file.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["#母類別", "子類別", "日期", "關係", "備註"])
            writer.writerows([(src, dst, "20261031", "contains", "")
                              for src, dst in edges])

    def graph(self, **kwargs):
        return draw_graph(files=(self.file,), metadata={
            "B": {"CT": "中文B"}, "C": {"CT": "中文C"}}, **kwargs)

    def test_bounded_subgraph_and_bfs_depth(self):
        self.write_edges([("A", "B"), ("A", "C"), ("B", "D"),
                          ("D", "A"), ("A", "B")])
        result = self.graph(root="A", depth=1, max_nodes=2)
        nodes = [e["data"]["id"] for e in result["elements"]
                 if "source" not in e["data"]]
        self.assertEqual(nodes, ["A", "B"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["nodes"], 2)
        self.assertEqual(result["edges"], 1)
        self.assertEqual(result["total_edges"], 4)
        self.assertEqual(result["elements"][1]["data"]["ct"], "中文B")
        self.assertTrue(result["elements"][0]["data"]["root"])

    def test_manual_expansion_retains_previous_nodes_and_is_bounded(self):
        self.write_edges([("A", "B"), ("B", "C"), ("C", "D")])
        first = self.graph(root="A", depth=1, max_nodes=3)
        second = self.graph(root="B", depth=1, max_nodes=3,
                            existing_nodes=("A", "B"))
        ids = {e["data"]["id"] for e in second["elements"]
               if "source" not in e["data"]}
        self.assertEqual(ids, {"A", "B", "C"})
        self.assertEqual(second["edges"], 2)
        limited = self.graph(root="C", depth=2, max_nodes=3,
                             existing_nodes=ids)
        self.assertTrue(limited["truncated"])
        self.assertEqual(limited["nodes"], 3)

    def test_unknown_root_bad_inputs_and_full_limit(self):
        self.write_edges([("A", "B"), ("B", "C")])
        with self.assertRaisesRegex(ValueError, "找不到類別"):
            self.graph(root="not-an-existing-class")
        with self.assertRaisesRegex(ValueError, "深度"):
            self.graph(root="A", depth=0)
        with self.assertRaisesRegex(ValueError, "上限"):
            self.graph(root="A", max_nodes=1001)
        with self.assertRaises(GraphLimitError):
            self.graph(root="A", existing_nodes=("A", "B", "C"), max_nodes=2)
        full = self.graph(full=True)
        self.assertEqual(full["nodes"], 3)
        self.assertEqual(full["edges"], 2)

    def test_file_changes_invalidate_cache(self):
        self.write_edges([("A", "B")])
        self.assertEqual(self.graph(root="A")["total_nodes"], 2)
        self.write_edges([("A", "B"), ("B", "C")])
        self.assertEqual(self.graph(root="A")["total_nodes"], 3)

    def test_real_taxonomy_uses_both_repository_files(self):
        self.assertEqual(TOPIC_FILES[0], DATA_DIR / "TopicTree.csv")
        self.assertTrue(all(path.exists() for path in TOPIC_FILES))
        edges, nodes, _adj = load_graph()
        self.assertGreaterEqual(len(nodes), 2670)
        self.assertGreaterEqual(len(edges), 3100)
        result = draw_graph(root="Spacetime Singularity Of Tree",
                            depth=2, max_nodes=DEFAULT_MAX_NODES)
        self.assertLessEqual(result["nodes"], DEFAULT_MAX_NODES)
        self.assertFalse(result["full"])
        self.assertGreater(result["nodes"], 1)
        self.assertLessEqual(result["edges"], result["total_edges"])

    def test_large_full_graph_is_rejected_before_render(self):
        self.write_edges([(f"N{i}", f"N{i+1}") for i in range(MAX_FULL_NODES)])
        with self.assertRaises(GraphLimitError):
            self.graph(full=True)


if __name__ == "__main__":
    unittest.main()
