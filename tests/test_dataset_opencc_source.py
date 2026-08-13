import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from DatasetConverter.opencc_source import convert_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class OpenCCConversionAdapterTests(unittest.TestCase):
    def test_passes_legacy_conversion_and_text_to_opencc(self):
        converter = Mock()
        converter.convert.return_value = "converted"
        constructor = Mock(return_value=converter)
        fake_module = types.SimpleNamespace(OpenCC=constructor)

        with patch.dict(sys.modules, {"opencc": fake_module}):
            result = convert_text("source text", "tw2s")

        self.assertEqual(result, "converted")
        constructor.assert_called_once_with("tw2s")
        converter.convert.assert_called_once_with("source text")

    def test_reader_and_adapter_have_no_module_scope_opencc_import(self):
        for relative_path in (
            "DatasetConverter/sampleHandler.py",
            "DatasetConverter/opencc_source.py",
        ):
            with self.subTest(path=relative_path):
                path = REPOSITORY_ROOT / relative_path
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
                imported_modules = {
                    alias.name
                    for node in tree.body
                    if isinstance(node, ast.Import)
                    for alias in node.names
                }
                imported_from = {
                    node.module
                    for node in tree.body
                    if isinstance(node, ast.ImportFrom)
                }

                self.assertNotIn("opencc", imported_modules)
                self.assertNotIn("opencc", imported_from)


if __name__ == "__main__":
    unittest.main()
