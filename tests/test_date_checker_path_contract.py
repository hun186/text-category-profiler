import ast
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import types
import unittest
from contextlib import redirect_stdout
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "DatasetConverter" / "DateChecker.py"


class DateCheckerSourceContractTests(unittest.TestCase):
    def test_source_has_guarded_bootstrap_and_guarded_workflow(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)

        self.assertNotIn("PackageImport", source)
        self.assertNotIn("PackageImporter.proc", source)
        self.assertNotIn("os.chdir", source)
        for machine_path in (
            "D:/shared/PythonModule",
            "Z:/PythonModule",
            "../PythonModule",
        ):
            self.assertNotIn(machine_path, source)

        bootstrap = 'Path(__file__).resolve().parents[1]'
        package_import = (
            "from text_category_profiler.data.DB_utils import sqlite3Query"
        )
        self.assertIn(bootstrap, source)
        self.assertLess(source.index(bootstrap), source.index(package_import))

        guarded_calls = []
        unguarded_calls = []
        for node in tree.body:
            if isinstance(node, ast.If) and ast.unparse(node.test) == "__name__ == '__main__'":
                guarded_calls.extend(ast.walk(node))
            elif not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                unguarded_calls.extend(ast.walk(node))

        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and ast.unparse(node.func) == "sys.path.insert"
                for node in guarded_calls
            )
        )
        self.assertTrue(
            any(
                isinstance(node, ast.Call) and ast.unparse(node.func) == "main"
                for node in guarded_calls
            )
        )
        forbidden_module_calls = {
            "sqlite3Query",
            "open",
            "iter",
            "next",
            "sys.path.insert",
            "os.chdir",
        }
        self.assertFalse(
            [
                ast.unparse(node.func)
                for node in unguarded_calls
                if isinstance(node, ast.Call)
                and ast.unparse(node.func) in forbidden_module_calls
            ]
        )

    def test_module_import_has_no_side_effects(self):
        program = textwrap.dedent(
            """
            import builtins
            import os
            import sys
            import types

            module = types.ModuleType("text_category_profiler.data.DB_utils")
            def forbidden_query(*args, **kwargs):
                raise AssertionError("sqlite3Query called")
            module.sqlite3Query = forbidden_query
            sys.modules[module.__name__] = module

            before_cwd = os.getcwd()
            before_path = list(sys.path)
            def forbidden(*args, **kwargs):
                raise AssertionError("filesystem side effect")
            builtins.open = forbidden
            os.chdir = forbidden
            import DatasetConverter.DateChecker
            assert os.getcwd() == before_cwd
            assert sys.path == before_path
            """
        )
        subprocess.run(
            [sys.executable, "-c", program],
            cwd=REPOSITORY_ROOT,
            check=True,
            text=True,
            capture_output=True,
        )

    def test_direct_script_bootstrap_preserves_caller_cwd(self):
        program = textwrap.dedent(
            f"""
            import builtins
            import os
            import runpy
            import sys

            repository_root = {str(REPOSITORY_ROOT)!r}
            script = {str(SCRIPT)!r}
            original_import = builtins.__import__
            expected_cwd = os.getcwd()
            def checked_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name == "text_category_profiler.data.DB_utils":
                    assert repository_root in sys.path
                    assert os.getcwd() == expected_cwd
                    raise SystemExit(23)
                return original_import(name, globals, locals, fromlist, level)
            builtins.__import__ = checked_import
            try:
                runpy.run_path(script, run_name="__main__")
            except SystemExit as error:
                assert error.code == 23
            else:
                raise AssertionError("DB_utils import was not intercepted")
            """
        )
        for caller_cwd in (REPOSITORY_ROOT, REPOSITORY_ROOT / "DatasetConverter"):
            with self.subTest(caller_cwd=caller_cwd):
                subprocess.run(
                    [sys.executable, "-c", program],
                    cwd=caller_cwd,
                    check=True,
                    text=True,
                    capture_output=True,
                )


class DateCheckerBehaviorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db_utils_stub = types.ModuleType("text_category_profiler.data.DB_utils")
        db_utils_stub.sqlite3Query = lambda *args, **kwargs: ()
        with mock.patch.dict(
            sys.modules,
            {"text_category_profiler.data.DB_utils": db_utils_stub},
        ):
            sys.modules.pop("DatasetConverter.DateChecker", None)
            import DatasetConverter.DateChecker as date_checker

        cls.date_checker = date_checker

    def test_legacy_base_directory_matrix(self):
        cases = {
            "/root/project": "/root/project",
            "/root/project/DatasetConverter": "/root/project",
            "/root/project/BertScript": "/root/project",
            "/tmp/random-caller": "/tmp/random-caller",
        }
        for caller_cwd, expected in cases.items():
            with self.subTest(caller_cwd=caller_cwd):
                self.assertEqual(
                    self.date_checker.resolve_legacy_base_directory(caller_cwd),
                    Path(expected),
                )

    def test_workflow_preserves_paths_query_results_and_cwd(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            legacy_base = Path(temporary_directory)
            dataset_directory = legacy_base / "DatasetConverter" / "dataset"
            dataset_directory.mkdir(parents=True)
            check_source = dataset_directory / "CheckSrc.csv"
            check_source.write_text("match-1\nmissing\nmatch-5\n", encoding="utf-8")
            expected_sqlite = dataset_directory / "top-1m_CZJ_SamplesFile.sql3"
            rows = [(f"match-{index}",) for index in range(10)]
            calls = []

            def sqlite_stub(path, query):
                calls.append((path, query, Path.cwd()))
                return rows

            original_cwd = Path.cwd()
            output = io.StringIO()
            try:
                os.chdir(legacy_base)
                caller_cwd = Path.cwd()
                with mock.patch.object(
                    self.date_checker, "sqlite3Query", side_effect=sqlite_stub
                ), redirect_stdout(output):
                    self.date_checker.main()
                self.assertEqual(Path.cwd(), caller_cwd)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(
                calls,
                [
                    (
                        str(expected_sqlite),
                        'SELECT text FROM sampleSrc WHERE OutLabel = "Benign Web Link";',
                        legacy_base,
                    )
                ],
            )
            stdout = output.getvalue()
            self.assertIn("contsSet", stdout)
            self.assertIn("match-1", stdout)
            self.assertIn("match-5", stdout)
            self.assertIn("2 of 3 are in TextPools.", stdout)


if __name__ == "__main__":
    unittest.main()
