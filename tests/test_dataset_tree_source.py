import sys
import types
import unittest
from unittest.mock import patch

from DatasetConverter.adapters.tree_source import closest_matching_parent
from DatasetConverter.adapters.tree_source import load_tree_files
from DatasetConverter.adapters.tree_source import subtopics
from DatasetConverter.adapters.tree_source import tree_nodes


class DatasetTreeSourceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        calls = self.calls
        self.module = types.ModuleType("ClassesTree.ClassesTree_utils")
        self.module.SetTreeFiles = (
            lambda **kwargs: calls.append(("load", kwargs)) or "tree-files"
        )
        self.module.GetNodes = lambda tree: calls.append(("nodes", tree)) or ["node"]
        self.module.GetSubTopics = (
            lambda topics, tree: calls.append(("subtopics", topics, tree))
            or ["child"]
        )
        self.module.GetClosestMatchingParent = (
            lambda tree, node, matches, **kwargs: calls.append(
                ("parent", tree, node, matches, kwargs)
            )
            or ["parent"]
        )

    def test_tree_operations_preserve_legacy_call_contracts(self):
        tree = [["root", "child"]]
        with patch.dict(sys.modules, {self.module.__name__: self.module}):
            self.assertEqual(tree_nodes(tree), ["node"])
            self.assertEqual(subtopics(["root"], tree), ["child"])
            self.assertEqual(
                closest_matching_parent(
                    tree,
                    "child",
                    {"root"},
                    ReturnOnlyOneClosestParent=True,
                ),
                ["parent"],
            )

        self.assertEqual(
            self.calls,
            [
                ("nodes", tree),
                ("subtopics", ["root"], tree),
                (
                    "parent",
                    tree,
                    "child",
                    {"root"},
                    {"ReturnOnlyOneClosestParent": True},
                ),
            ],
        )

    def test_tree_file_loading_forwards_keywords(self):
        kwargs = {
            "TreeBaseFNList": ["TopicTree.csv"],
            "OutputPath": "records",
            "OnlyLettersDigitsLabels": False,
            "TreeSourceDir": "taxonomy",
        }
        with patch.dict(sys.modules, {self.module.__name__: self.module}):
            self.assertEqual(load_tree_files(**kwargs), "tree-files")

        self.assertEqual(self.calls, [("load", kwargs)])


if __name__ == "__main__":
    unittest.main()
