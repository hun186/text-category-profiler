"""BL-001 Graph_utils import contract without third-party or runtime service loads."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "text_category_profiler" / "visualization" / "Graph_utils.py"
MODULE = "text_category_profiler.core.utilities"


def graph_tree():
    return ast.parse(GRAPH.read_text(encoding="utf-8"), filename=str(GRAPH))


def flatten_import():
    """Return the actual canonical import statement from the tracked source."""
    matches = [
        node for node in graph_tree().body
        if isinstance(node, ast.ImportFrom)
        and node.module == MODULE
        and any(alias.name == "flattenList" for alias in node.names)
    ]
    if len(matches) != 1:
        raise AssertionError("Exactly one unguarded canonical flattenList import required")
    return matches[0]


class GraphUtilsCanonicalImportTests(unittest.TestCase):
    def test_no_ambiguous_bare_import_or_exception_fallback(self):
        tree = graph_tree()
        imports = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and any(alias.name == "flattenList" for alias in node.names)
        ]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module, MODULE)
        self.assertEqual(flatten_import().level, 0)
        self.assertFalse(any(
            isinstance(node, ast.ImportFrom) and node.module == "utilities"
            for node in ast.walk(tree)
        ))

    def test_import_failure_is_not_swallowed_or_retried_with_bare_module(self):
        statement = ast.Module(body=[flatten_import()], type_ignores=[])
        attempted = []
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            attempted.append(name)
            if name == MODULE:
                raise RuntimeError("canonical provider failed")
            if name == "utilities":
                raise AssertionError("bare fallback must never run")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(RuntimeError, "canonical provider failed"):
                exec(compile(statement, str(GRAPH), "exec"), {})
        self.assertEqual(attempted, [MODULE])

    def test_compute_component_preserves_connected_groups(self):
        funcs = [
            x for x in graph_tree().body
            if isinstance(x, ast.FunctionDef) and x.name == "ComputeComponent"
        ]
        self.assertEqual(len(funcs), 1)
        scope = {
            "flattenList": lambda edges: [part for edge in edges for part in edge],
        }
        exec(
            compile(ast.Module(body=funcs, type_ignores=[]), str(GRAPH), "exec"),
            scope,
        )
        graph, membership = scope["ComputeComponent"]([
            ("a", "b"), ("b", "c"), ("z", "y"),
        ])
        self.assertEqual(
            {frozenset(group) for group in graph.values()},
            {frozenset({"a", "b", "c"}), frozenset({"y", "z"})},
        )
        for group_id, nodes in graph.items():
            self.assertTrue(all(membership[node] == group_id for node in nodes))

    def test_empty_edge_behavior_is_unchanged(self):
        fn = next(
            x for x in graph_tree().body
            if isinstance(x, ast.FunctionDef) and x.name == "ComputeComponent"
        )
        scope = {"flattenList": lambda edges: [x for edge in edges for x in edge]}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(GRAPH), "exec"), scope)
        self.assertEqual(scope["ComputeComponent"]([]), ({}, {}))

    def test_legacy_dataset_converter_imports_are_not_changed_in_this_batch(self):
        texts = [
            (ROOT / path).read_text(encoding="utf-8")
            for path in ["DatasetConverter/df_utils.py", "DatasetConverter/old_MP_utils.py"]
        ]
        self.assertIn("from DatasetConverter.old_MP_utils import MPlogger, multicoreJob", texts[0])
        self.assertIn("from text_category_profiler.concurrency.MP_utils import timeNow", texts[1])


if __name__ == "__main__":
    unittest.main()
