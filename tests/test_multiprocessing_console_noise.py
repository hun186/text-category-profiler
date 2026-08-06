import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class MultiprocessingConsoleNoiseTests(unittest.TestCase):
    def test_training_notice_is_limited_to_main_process(self):
        source = (REPOSITORY_ROOT / "PythonModule/utils/pipeline/TCF_utils.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('current_process().name == "MainProcess"', source)

    def test_data_converter_does_not_import_dash_at_module_scope(self):
        path = REPOSITORY_ROOT / "DatasetConverter/DataConverter.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        module_scope_imports = [
            node
            for node in module.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]

        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "utils.visualization.Dash_utils"
                for node in module_scope_imports
            )
        )

    def test_ext_converter_imports_do_not_print_current_directory(self):
        for relative_path in (
            "DatasetConverter/EXTConverter/Combiner.py",
            "DatasetConverter/EXTConverter/ExtractionConverter.py",
        ):
            source = (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn('print(f"cwd:', source)


if __name__ == "__main__":
    unittest.main()
