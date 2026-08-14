import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_CONVERTER = REPOSITORY_ROOT / "DatasetConverter" / "DataConverter.py"


class DataConverterImportBoundaryTests(unittest.TestCase):
    def test_entrypoint_does_not_import_unused_psutil(self):
        tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        module_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        from_imports = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn("psutil", module_imports)
        self.assertNotIn("psutil", from_imports)

    def test_entrypoint_does_not_import_unused_colorama(self):
        tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        from_imports = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("colorama", from_imports)

if __name__ == "__main__":
    unittest.main()
