import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from DatasetConverter.label_source import labels_from_path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "ClassesTree.Label_utils"


class DatasetLabelSourceTests(unittest.TestCase):
    def test_adapter_preserves_legacy_keyword_contract(self):
        calls = []
        fake_module = types.ModuleType(MODULE_NAME)

        def fake_get_labels(path, **kwargs):
            calls.append((path, kwargs))
            return ["Diplomacy"]

        fake_module.getLabelsFromFileName = fake_get_labels
        with patch.dict(sys.modules, {MODULE_NAME: fake_module}):
            result = labels_from_path(
                "#T#[diplomacy]/fixture.txt",
                unique_sorted=False,
                only_letters_digits=True,
            )

        self.assertEqual(result, ["Diplomacy"])
        self.assertEqual(
            calls,
            [
                (
                    "#T#[diplomacy]/fixture.txt",
                    {"UniqueSorted": False, "OnlyLettersDigits": True},
                )
            ],
        )

    def test_reader_and_adapter_have_no_module_scope_legacy_import(self):
        for relative_path in (
            "DatasetConverter/sampleHandler.py",
            "DatasetConverter/label_source.py",
        ):
            tree = ast.parse(
                (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
            )
            module_imports = [
                node.module
                for node in tree.body
                if isinstance(node, ast.ImportFrom)
            ]
            self.assertNotIn(MODULE_NAME, module_imports, relative_path)


if __name__ == "__main__":
    unittest.main()
