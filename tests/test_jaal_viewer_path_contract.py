import ast
import builtins
import importlib
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "ClassesTree" / "Visualization" / "jaal" / "jaalViewer.py"
MODULE_NAME = "ClassesTree.Visualization.jaal.jaalViewer"


class LoadTreeSentinel(Exception):
    pass


def dependency_stubs():
    jaal = types.ModuleType("jaal")
    jaal.__path__ = []
    jaal.Jaal = object
    jaal_datasets = types.ModuleType("jaal.datasets")
    jaal_datasets.load_got = lambda: None

    pandas = types.ModuleType("pandas")
    pandas.DataFrame = object

    tree_utils = types.ModuleType("ClassesTree.ClassesTree_utils")
    for name in (
        "LoadTree",
        "GetSubTopics",
        "BuildSubTopicsDict",
        "GetRoots",
        "BuildInfoScoreTable",
        "CountDegree",
    ):
        setattr(tree_utils, name, lambda *args, **kwargs: None)

    longest_path = types.ModuleType("ClassesTree.longestPath")
    longest_path.longestPath = lambda *args, **kwargs: None

    utilities = types.ModuleType("text_category_profiler.core.utilities")
    utilities.str2bool = lambda value: bool(value)
    df_utils = types.ModuleType("text_category_profiler.data.df_utils")
    df_utils.flattenList = lambda value: value

    return {
        "jaal": jaal,
        "jaal.datasets": jaal_datasets,
        "pandas": pandas,
        "ClassesTree.ClassesTree_utils": tree_utils,
        "ClassesTree.longestPath": longest_path,
        "text_category_profiler.core.utilities": utilities,
        "text_category_profiler.data.df_utils": df_utils,
    }


def import_viewer():
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


class JaalViewerPathContractTests(unittest.TestCase):
    def test_source_contract_uses_direct_script_bootstrap_before_local_imports(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("PackageImport", imported_modules)
        self.assertNotIn("PackageImporter.proc", source)
        self.assertNotIn("os.chdir", source)
        self.assertNotIn('.index("TopicClassification")', source)
        for forbidden in ("D:/shared/PythonModule", "Z:/PythonModule", "../PythonModule"):
            self.assertNotIn(forbidden, source)

        root_assignment = next(
            node for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "REPOSITORY_ROOT"
                    for target in node.targets)
        )
        self.assertIn("Path(__file__).resolve().parents[3]", ast.unparse(root_assignment))

        main_guard = next(
            node for node in tree.body
            if isinstance(node, ast.If)
            and "__name__ == '__main__'" in ast.unparse(node.test)
        )
        inserts = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "insert"
            and ast.unparse(node.func.value) == "sys.path"
        ]
        self.assertEqual(len(inserts), 1)
        self.assertIn(inserts[0], list(ast.walk(main_guard)))

        first_local_import = min(
            node.lineno for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module.startswith(("ClassesTree.", "text_category_profiler."))
        )
        self.assertLess(main_guard.lineno, first_local_import)
        self.assertIn('TREE_SOURCE_DIR = REPOSITORY_ROOT / "ClassesTree" / "data"', source)
        self.assertIn('TREE_SOURCE_DIR / "TopicTree.csv"', source)
        self.assertIn('TREE_SOURCE_DIR / "TopicTree_AK4.csv"', source)

    def test_normal_import_does_not_mutate_cwd_or_sys_path(self):
        original_cwd = os.getcwd()
        original_path = list(sys.path)
        with mock.patch.dict(sys.modules, dependency_stubs()), mock.patch(
            "os.chdir", side_effect=AssertionError("import must not call os.chdir")
        ) as chdir:
            module = import_viewer()

        self.assertEqual(os.getcwd(), original_cwd)
        self.assertEqual(sys.path, original_path)
        chdir.assert_not_called()
        self.assertEqual(module.REPOSITORY_ROOT, REPOSITORY_ROOT)

    def test_direct_script_bootstrap_is_cwd_independent(self):
        jaal_dir = SCRIPT.parent
        with tempfile.TemporaryDirectory() as temporary_directory:
            for caller_cwd in (REPOSITORY_ROOT, jaal_dir, Path(temporary_directory)):
                with self.subTest(caller_cwd=caller_cwd):
                    original_cwd = os.getcwd()
                    original_path = list(sys.path)
                    real_import = builtins.__import__

                    def intercept(name, *args, **kwargs):
                        if name == "ClassesTree.ClassesTree_utils":
                            self.assertIn(str(REPOSITORY_ROOT), sys.path)
                            self.assertEqual(Path.cwd(), caller_cwd)
                            raise SystemExit("repository import reached")
                        return real_import(name, *args, **kwargs)

                    try:
                        os.chdir(caller_cwd)
                        with mock.patch.dict(sys.modules, dependency_stubs()), mock.patch(
                            "builtins.__import__", side_effect=intercept
                        ), self.assertRaisesRegex(SystemExit, "repository import reached"):
                            runpy.run_path(str(SCRIPT), run_name="__main__")
                        self.assertEqual(Path.cwd(), caller_cwd)
                    finally:
                        os.chdir(original_cwd)
                        sys.path[:] = original_path

    def test_jaal_view_main_passes_canonical_absolute_taxonomy_paths(self):
        with mock.patch.dict(sys.modules, dependency_stubs()):
            module = import_viewer()

        received = []

        def capture(files):
            received.extend(files)
            raise LoadTreeSentinel

        with mock.patch.object(module, "LoadTree", side_effect=capture), self.assertRaises(
            LoadTreeSentinel
        ):
            module.JaalViewMain()

        expected = [
            REPOSITORY_ROOT / "ClassesTree" / "data" / "TopicTree.csv",
            REPOSITORY_ROOT / "ClassesTree" / "data" / "TopicTree_AK4.csv",
        ]
        self.assertEqual(received, [str(path) for path in expected])
        self.assertTrue(all(Path(path).is_absolute() for path in received))
        self.assertNotIn("TopicTree.csv", received)
        self.assertNotIn("TopicTree_AK4.csv", received)

    def test_caller_cwd_taxonomy_files_cannot_shadow_repository_files(self):
        with mock.patch.dict(sys.modules, dependency_stubs()):
            module = import_viewer()

        received = []
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            for filename in ("TopicTree.csv", "TopicTree_AK4.csv"):
                (temporary_path / filename).write_text("caller sentinel", encoding="utf-8")
            try:
                os.chdir(temporary_path)
                with mock.patch.object(
                    module,
                    "LoadTree",
                    side_effect=lambda files: (received.extend(files), (_ for _ in ()).throw(LoadTreeSentinel))[1],
                ), self.assertRaises(LoadTreeSentinel):
                    module.JaalViewMain()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(received, [str(path) for path in module.TREE_FILES])
        self.assertTrue(all(Path(path).parent == REPOSITORY_ROOT / "ClassesTree" / "data" for path in received))

    def test_repository_contains_complete_canonical_pair_not_jaal_local_pair(self):
        canonical = REPOSITORY_ROOT / "ClassesTree" / "data"
        self.assertTrue((canonical / "TopicTree.csv").is_file())
        self.assertTrue((canonical / "TopicTree_AK4.csv").is_file())
        self.assertTrue((SCRIPT.parent / "TopicTree.csv").is_file())
        self.assertFalse((SCRIPT.parent / "TopicTree_AK4.csv").exists())


if __name__ == "__main__":
    unittest.main()
