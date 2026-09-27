import ast
import json
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "DatasetConverter" / "SummarizationExcels_Combiner.py"


class SummarizationExcelsCombinerPathContractTests(unittest.TestCase):
    def test_source_uses_only_main_guarded_file_relative_bootstrap(self):
        source = SCRIPT.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=str(SCRIPT))

        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("PackageImport", imported_modules)
        self.assertNotIn("PackageImporter.proc()", source)
        self.assertNotIn("D:/shared/PythonModule", source)
        self.assertNotIn("Z:/PythonModule", source)
        self.assertNotIn("../PythonModule", source)

        main_guard = next(
            node
            for node in tree.body
            if isinstance(node, ast.If)
            and ast.unparse(node.test) == "__name__ == '__main__'"
        )
        main_source = ast.unparse(main_guard)
        self.assertIn("Path(__file__).resolve().parents[1]", main_source)
        self.assertIn("sys.path.insert(0, str(REPOSITORY_ROOT))", main_source)

        module_scope = ast.Module(
            body=[node for node in tree.body if node is not main_guard],
            type_ignores=[],
        )
        module_scope_source = ast.unparse(module_scope)
        self.assertNotIn("os.chdir(", module_scope_source)
        self.assertNotIn("sys.path.", module_scope_source)

    def test_direct_script_from_repository_root_preserves_cwd_output_contract(self):
        self._assert_direct_script_contract(REPOSITORY_ROOT)

    def test_direct_script_from_dataset_converter_preserves_cwd_output_contract(self):
        self._assert_direct_script_contract(REPOSITORY_ROOT / "DatasetConverter")

    def _assert_direct_script_contract(self, caller_cwd):
        harness = textwrap.dedent(
            """
            import builtins
            import importlib.util
            import json
            import os
            import runpy
            import sys
            import types

            script, repository_root = sys.argv[1:]
            original_cwd = os.getcwd()
            observed = {}
            real_import = builtins.__import__

            class Frame:
                shape = (0, 0)
                def dropna(self, inplace=False): pass
                def reset_index(self, inplace=False, drop=False): pass

            pandas = types.ModuleType("pandas")
            pandas.DataFrame = Frame
            pandas.concat = lambda frames, ignore_index=False: Frame()
            setproctitle = types.ModuleType("setproctitle")
            setproctitle.setproctitle = lambda title: None

            utilities = types.ModuleType("text_category_profiler.core.utilities")
            utilities.OSWALK = lambda path: []
            utilities.getFNFromFullPath = lambda path: path
            df_utils = types.ModuleType("text_category_profiler.data.df_utils")
            class Output:
                def __init__(self, frame, output_main, **kwargs):
                    observed["output_main"] = output_main
                def run(self): pass
            df_utils.dfOutputer = Output
            df_utils.XLSTodf = lambda **kwargs: Frame()
            mp_utils = types.ModuleType("text_category_profiler.concurrency.MP_utils")
            mp_utils.multicoreJob = object
            mp_utils.MPlogger = object
            stubs = {
                "pandas": pandas,
                "setproctitle": setproctitle,
                utilities.__name__: utilities,
                df_utils.__name__: df_utils,
                mp_utils.__name__: mp_utils,
            }

            def checked_import(name, globals=None, locals=None, fromlist=(), level=0):
                if name in stubs:
                    if name.startswith("text_category_profiler."):
                        spec = importlib.util.find_spec(name)
                        if spec is None:
                            raise AssertionError("repo-local import is not resolvable: " + name)
                    return stubs[name]
                return real_import(name, globals, locals, fromlist, level)

            builtins.__import__ = checked_import
            os.system = lambda command: 0
            runpy.run_path(script, run_name="__main__")
            print("CONTRACT=" + json.dumps({
                "cwd_before": original_cwd,
                "cwd_after": os.getcwd(),
                "output_main": observed["output_main"],
                "repo_on_path": repository_root in sys.path,
            }))
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", harness, str(SCRIPT), str(REPOSITORY_ROOT)],
            cwd=caller_cwd,
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(
            next(
                line.removeprefix("CONTRACT=")
                for line in completed.stdout.splitlines()
                if line.startswith("CONTRACT=")
            )
        )
        expected_cwd = str(caller_cwd)
        self.assertEqual(payload["cwd_before"], expected_cwd)
        self.assertEqual(payload["cwd_after"], expected_cwd)
        self.assertEqual(
            payload["output_main"], str(caller_cwd / "SummarizationTrain")
        )
        self.assertTrue(payload["repo_on_path"])


if __name__ == "__main__":
    unittest.main()
