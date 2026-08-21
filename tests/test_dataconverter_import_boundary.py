import ast
import subprocess
import sys
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DATA_CONVERTER = REPOSITORY_ROOT / "DatasetConverter" / "DataConverter.py"
EXTRACTION_ADAPTER = (
    REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "extraction_source.py"
)
STAGE_UTILS = REPOSITORY_ROOT / "DatasetConverter" / "core" / "stage_utils.py"
PIPELINE_ADAPTER = (
    REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "pipeline_source.py"
)
TREE_ADAPTER = REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "tree_source.py"
RUNTIME_ADAPTER = (
    REPOSITORY_ROOT / "DatasetConverter" / "adapters" / "runtime_source.py"
)


class DataConverterImportBoundaryTests(unittest.TestCase):
    def test_entrypoint_does_not_import_application_parameter_bootstrap(self):
        tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        from_imports = {
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn("TCF_Params.TCFParameters", from_imports)
        self.assertNotIn("DatasetConverter.ConverterParameters", from_imports)

    def test_entrypoint_import_advances_past_parameter_bootstrap(self):
        script = """
import importlib.abc
import sys

class RejectParameterBootstrap(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {
            'TCF_Params.TCFParameters',
            'DatasetConverter.ConverterParameters',
        }:
            raise AssertionError('DataConverter imported legacy parameter bootstrap')
        return None

sys.meta_path.insert(0, RejectParameterBootstrap())
try:
    import DatasetConverter.DataConverter
except ModuleNotFoundError:
    # Later optional/runtime boundaries are intentionally outside this slice.
    pass
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_extraction_dependencies_are_feature_activated(self):
        entrypoint_tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        adapter_tree = ast.parse(EXTRACTION_ADAPTER.read_text(encoding="utf-8"))
        forbidden = {
            "DatasetConverter.EXTConverter.ExtractionConverter",
            "DatasetConverter.EXTConverter.ExtractionRule",
            "DatasetConverter.EXTConverter.Combiner",
        }

        entrypoint_imports = {
            node.module
            for node in entrypoint_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        adapter_imports = {
            node.module
            for node in adapter_tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertTrue(forbidden.isdisjoint(entrypoint_imports))
        self.assertTrue(forbidden.isdisjoint(adapter_imports))

    def test_entrypoint_uses_dependency_light_stage_utilities(self):
        entrypoint_tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        stage_utils_tree = ast.parse(STAGE_UTILS.read_text(encoding="utf-8"))

        entrypoint_imports = {
            node.module
            for node in entrypoint_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        stage_utils_imports = {
            node.module
            for node in stage_utils_tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn("text_category_profiler.core.utilities", entrypoint_imports)
        self.assertNotIn("text_category_profiler.core.utilities", stage_utils_imports)

    def test_shared_pipeline_runtime_is_feature_activated(self):
        entrypoint_tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        adapter_tree = ast.parse(PIPELINE_ADAPTER.read_text(encoding="utf-8"))

        entrypoint_imports = {
            node.module
            for node in entrypoint_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        adapter_imports = {
            node.module
            for node in adapter_tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn("text_category_profiler.pipeline.TCF_utils", entrypoint_imports)
        self.assertNotIn("text_category_profiler.pipeline.TCF_utils", adapter_imports)
        self.assertNotIn(
            "text_category_profiler.pipeline.DataConverter_utils",
            entrypoint_imports,
        )
        self.assertNotIn(
            "text_category_profiler.pipeline.DataConverter_utils",
            adapter_imports,
        )

    def test_class_tree_runtime_is_feature_activated(self):
        entrypoint_tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        adapter_tree = ast.parse(TREE_ADAPTER.read_text(encoding="utf-8"))

        entrypoint_imports = {
            node.module
            for node in entrypoint_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        adapter_imports = {
            node.module
            for node in adapter_tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertNotIn("ClassesTree.ClassesTree_utils", entrypoint_imports)
        self.assertNotIn("ClassesTree.ClassesTree_utils", adapter_imports)

    def test_numpy_and_pandas_runtime_is_feature_activated(self):
        entrypoint_tree = ast.parse(DATA_CONVERTER.read_text(encoding="utf-8"))
        adapter_tree = ast.parse(RUNTIME_ADAPTER.read_text(encoding="utf-8"))
        forbidden = {
            "text_category_profiler.concurrency.MP_utils",
            "text_category_profiler.data.DB_utils",
            "text_category_profiler.data.df_utils",
        }

        entrypoint_imports = {
            node.module
            for node in entrypoint_tree.body
            if isinstance(node, ast.ImportFrom)
        }
        adapter_imports = {
            node.module
            for node in adapter_tree.body
            if isinstance(node, ast.ImportFrom)
        }

        self.assertTrue(forbidden.isdisjoint(entrypoint_imports))
        self.assertTrue(forbidden.isdisjoint(adapter_imports))

    def test_entrypoint_import_does_not_activate_conversion_runtime(self):
        script = """
import importlib.abc
import sys

class RejectConversionRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {
            'text_category_profiler.concurrency.MP_utils',
            'text_category_profiler.data.DB_utils',
            'text_category_profiler.data.df_utils',
        }:
            raise AssertionError('DataConverter activated conversion runtime')
        return None

sys.meta_path.insert(0, RejectConversionRuntime())
import DatasetConverter.DataConverter
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
