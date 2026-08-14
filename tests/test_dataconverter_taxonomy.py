import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace

from DatasetConverter.taxonomy import load_taxonomy
from DatasetConverter.taxonomy import taxonomy_config_from_namespace
from DatasetConverter.taxonomy import validate_taxonomy


class TaxonomyValidationTests(unittest.TestCase):
    def test_normalizes_labels_and_reports_missing_score_entries(self):
        result = validate_taxonomy(
            [["TopicB", "TopicA"], ["TopicA", "TopicC"]],
            ["TopicA", "TopicC"],
        )

        self.assertEqual(result.labels, ("TopicA", "TopicB", "TopicC"))
        self.assertEqual(result.missing_info_score_labels, ("TopicB",))
        self.assertFalse(result.is_binary)

    def test_identifies_binary_taxonomy_independent_of_branch_order(self):
        result = validate_taxonomy(
            [["Positive"], ["Negative"]],
            ["Negative", "Positive"],
        )

        self.assertTrue(result.is_binary)
        self.assertEqual(result.missing_info_score_labels, ())

    def test_maps_namespace_to_immutable_loader_config(self):
        config = taxonomy_config_from_namespace(
            SimpleNamespace(
                TopicTreeFiles=" TopicTree.csv, custom.csv ,,",
                TopicTreeDir="taxonomy-input",
                BertDatasetSubDir="dataset-output",
            )
        )

        self.assertEqual(config.source_files, ("TopicTree.csv", "custom.csv"))
        self.assertEqual(config.source_directory, "taxonomy-input")
        self.assertEqual(
            config.record_directory, os.path.join("dataset-output", "OnlyForRecord")
        )
        with self.assertRaises(AttributeError):
            config.source_directory = "changed"

    def test_loader_receives_normalized_config_and_returns_named_result(self):
        calls = []

        def fake_loader(**kwargs):
            calls.append(kwargs)
            return [["Root", "Child"]], {"Root": 1.0}

        config = taxonomy_config_from_namespace(
            SimpleNamespace(
                TopicTreeFiles="tree.csv",
                TopicTreeDir="source",
                BertDatasetSubDir="output",
            )
        )
        result = load_taxonomy(config, loader=fake_loader)

        self.assertEqual(calls, [{
            "TreeBaseFNList": ["tree.csv"],
            "OutputPath": os.path.join("output", "OnlyForRecord"),
            "TreeSourceDir": "source",
        }])
        self.assertEqual(result.tree, [["Root", "Child"]])
        self.assertEqual(result.validation.labels, ("Child", "Root"))
        self.assertEqual(result.validation.missing_info_score_labels, ("Child",))

    def test_load_labels_has_no_mutable_default_and_uses_named_loader(self):
        source = Path("DatasetConverter/DataConverter.py").read_text(encoding="utf-8")
        module = ast.parse(source)
        functions = {
            node.name: node
            for node in module.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        load_labels = functions["loadLabels"]
        self.assertIsInstance(load_labels.args.defaults[-1], ast.Constant)
        self.assertIsNone(load_labels.args.defaults[-1].value)
        calls = [
            node.func.id
            for node in ast.walk(load_labels)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        self.assertIn("load_taxonomy", calls)
        self.assertNotIn("SetTreeFiles", calls)


if __name__ == "__main__":
    unittest.main()
