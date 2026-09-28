import ast
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "DatasetConverter" / "ConverterParameters.py"


def run_python(source, cwd):
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


def is_main_guard(node):
    return (
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and any(
            isinstance(comparator, ast.Constant)
            and comparator.value == "__main__"
            for comparator in node.test.comparators
        )
    )


def is_sys_path_insert(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "insert"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "path"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "sys"
    )


class ConverterParametersPathContractTests(unittest.TestCase):
    def test_source_uses_only_a_direct_script_repository_bootstrap(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("PackageImport", imported_modules)
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "proc"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "PackageImporter"
                for node in ast.walk(tree)
            )
        )
        self.assertNotIn("D:/shared/PythonModule", source)
        self.assertNotIn("Z:/PythonModule", source)
        self.assertNotIn("../PythonModule", source)
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "chdir"
                for node in ast.walk(tree)
            )
        )
        self.assertIn("Path(__file__).resolve().parents[1]", source)

        package_import = next(
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom)
            and node.module == "text_category_profiler.concurrency.MP_utils"
        )
        main_guards = [
            (index, node)
            for index, node in enumerate(tree.body)
            if is_main_guard(node)
        ]
        self.assertEqual(len(main_guards), 1)
        bootstrap_index, bootstrap = main_guards[0]
        self.assertLess(bootstrap_index, package_import)
        self.assertEqual(
            sum(is_sys_path_insert(node) for node in ast.walk(tree)),
            1,
        )
        self.assertTrue(any(is_sys_path_insert(node) for node in ast.walk(bootstrap)))

    def test_import_preserves_runtime_probes_without_bootstrapping_sys_path(self):
        result = run_python(
            f"""
            import sys
            import types

            repository_root = {str(REPOSITORY_ROOT)!r}
            sys.path.insert(0, repository_root)

            events = []
            gpu = types.ModuleType("GPUtil")
            def get_available():
                events.append(("getAvailable",))
                return ["gpu-sentinel"]
            gpu.getAvailable = get_available
            sys.modules["GPUtil"] = gpu

            package = types.ModuleType("text_category_profiler")
            package.__path__ = []
            concurrency = types.ModuleType("text_category_profiler.concurrency")
            concurrency.__path__ = []
            mp_utils = types.ModuleType("text_category_profiler.concurrency.MP_utils")
            class FakeMulticoreJob:
                def __init__(self):
                    events.append(("construct",))
                def ComputeNProcess(self, log=False):
                    events.append(("ComputeNProcess", log))
                    return 17
                def ComputeSPCNProcess(self, log=False):
                    events.append(("ComputeSPCNProcess", log))
                    return 23
            mp_utils.multicoreJob = FakeMulticoreJob
            sys.modules["text_category_profiler"] = package
            sys.modules["text_category_profiler.concurrency"] = concurrency
            sys.modules["text_category_profiler.concurrency.MP_utils"] = mp_utils

            before = list(sys.path)
            import DatasetConverter.ConverterParameters as cp
            after = list(sys.path)

            assert before == after, (before, after)
            assert cp.GPUDevices == ["gpu-sentinel"]
            assert cp.nProcess == 17
            assert cp.nProcessSPC == 23
            assert events == [
                ("getAvailable",),
                ("construct",),
                ("ComputeNProcess", False),
                ("construct",),
                ("ComputeSPCNProcess", False),
            ], events
            print("IMPORT_PROBES_AND_PATH_OK")
            """,
            REPOSITORY_ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("IMPORT_PROBES_AND_PATH_OK", result.stdout)

    def test_direct_script_bootstrap_preserves_each_caller_cwd(self):
        for caller_cwd in (REPOSITORY_ROOT, REPOSITORY_ROOT / "DatasetConverter"):
            with self.subTest(caller_cwd=caller_cwd):
                result = run_python(
                    f"""
                    import builtins
                    import os
                    import runpy
                    import sys
                    import types

                    repository_root = {str(REPOSITORY_ROOT)!r}
                    script = {str(SCRIPT)!r}
                    original_cwd = os.getcwd()
                    sys.path = [path for path in sys.path if path != repository_root]

                    gpu = types.ModuleType("GPUtil")
                    gpu.getAvailable = lambda: ["unused"]
                    sys.modules["GPUtil"] = gpu
                    original_import = builtins.__import__

                    def checked_import(name, *args, **kwargs):
                        if name == "text_category_profiler.concurrency.MP_utils":
                            assert repository_root in sys.path
                            assert os.getcwd() == original_cwd
                            print("BOOTSTRAP_AND_CWD_OK")
                            raise SystemExit(0)
                        return original_import(name, *args, **kwargs)

                    builtins.__import__ = checked_import
                    runpy.run_path(script, run_name="__main__")
                    raise AssertionError("MP_utils import was not observed")
                    """,
                    caller_cwd,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("BOOTSTRAP_AND_CWD_OK", result.stdout)


if __name__ == "__main__":
    unittest.main()
