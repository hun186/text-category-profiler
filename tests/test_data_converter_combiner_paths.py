import ast
import os
import unittest
from pathlib import Path

from DatasetConverter.combiner_paths import resolve_repository_path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DataConverterCombinerPathTests(unittest.TestCase):
    def test_repository_relative_runtime_paths_preserve_legacy_locations(self):
        original_cwd = os.getcwd()
        cases = {
            "WorkPool": REPOSITORY_ROOT / "WorkPool",
            "BigDataWarehouse/論文/ScientificResearch": (
                REPOSITORY_ROOT / "BigDataWarehouse/論文/ScientificResearch"
            ),
            "logs": REPOSITORY_ROOT / "logs",
            "DatasetConverter/train": REPOSITORY_ROOT / "DatasetConverter/train",
        }

        for configured_path, expected in cases.items():
            with self.subTest(configured_path=configured_path):
                self.assertEqual(
                    resolve_repository_path(configured_path, REPOSITORY_ROOT),
                    str(expected),
                )

        self.assertEqual(os.getcwd(), original_cwd)

    def test_absolute_runtime_path_is_unchanged(self):
        absolute_path = str(REPOSITORY_ROOT / "external-data")

        self.assertEqual(
            resolve_repository_path(absolute_path, REPOSITORY_ROOT),
            absolute_path,
        )

    def test_direct_script_resolves_each_cwd_relative_runtime_path(self):
        source_path = REPOSITORY_ROOT / "DatasetConverter/DataConverter_Combiner.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8-sig"))
        resolved_values = [
            ast.unparse(node.args[0])
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) == "resolve_repository_path"
        ]

        self.assertCountEqual(
            resolved_values,
            ["WorkPoolROOT", "path", "'logs'", "'DatasetConverter/train'"],
        )


if __name__ == "__main__":
    unittest.main()
