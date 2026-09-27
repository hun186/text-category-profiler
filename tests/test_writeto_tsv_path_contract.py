import ast
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "BertScript" / "writeto_tsv.py"


def run_python(source, cwd):
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(source)],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=False,
    )


class WriteToTsvPathContractTests(unittest.TestCase):
    def test_source_uses_only_a_direct_script_repository_bootstrap(self):
        source = SCRIPT.read_text(encoding="utf-8")
        tree = ast.parse(source)

        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertNotIn("PackageImport", imported_modules)
        self.assertNotIn("PackageImporter", source)
        self.assertNotIn("D:/shared/PythonModule", source)
        self.assertNotIn("Z:/PythonModule", source)
        self.assertNotIn("../PythonModule", source)
        self.assertNotIn("os.chdir", source)
        self.assertIn("Path(__file__).resolve().parents[1]", source)

        utilities_import = next(
            index
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.ImportFrom)
            and node.module == "text_category_profiler.core.utilities"
        )
        main_guards = [
            (index, node)
            for index, node in enumerate(tree.body)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
            and any(
                isinstance(comparator, ast.Constant)
                and comparator.value == "__main__"
                for comparator in node.test.comparators
            )
        ]
        self.assertEqual(len(main_guards), 2)
        bootstrap_index, bootstrap = main_guards[0]
        self.assertLess(bootstrap_index, utilities_import)
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "insert"
                for node in ast.walk(bootstrap)
            )
        )

        unguarded_calls = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.If)):
                continue
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    name = getattr(child.func, "id", None)
                    if name in {"MKDIR", "PickSamples", "WriteTo_tsv"}:
                        unguarded_calls.append(name)
        self.assertEqual(unguarded_calls, [])

    def test_import_has_no_dataset_or_cwd_side_effects(self):
        result = run_python(
            f"""
            import builtins
            import os
            import random
            import sys
            import types

            root = {str(REPOSITORY_ROOT)!r}
            sys.path.insert(0, root)
            original_cwd = os.getcwd()

            package = types.ModuleType("text_category_profiler")
            package.__path__ = []
            core = types.ModuleType("text_category_profiler.core")
            core.__path__ = []
            utilities = types.ModuleType("text_category_profiler.core.utilities")
            def fail_mkdir(*args, **kwargs):
                raise AssertionError("MKDIR called during import")
            utilities.MKDIR = fail_mkdir
            sys.modules["text_category_profiler"] = package
            sys.modules["text_category_profiler.core"] = core
            sys.modules["text_category_profiler.core.utilities"] = utilities

            os.listdir = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("os.listdir called during import")
            )
            builtins.open = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("open called during import")
            )
            random.sample = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("random.sample called during import")
            )
            random.shuffle = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("random.shuffle called during import")
            )

            import BertScript.writeto_tsv
            assert os.getcwd() == original_cwd
            print("IMPORT_SIDE_EFFECT_FREE")
            """,
            REPOSITORY_ROOT,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("IMPORT_SIDE_EFFECT_FREE", result.stdout)

    def test_direct_script_bootstrap_preserves_each_caller_cwd(self):
        for caller_cwd in (REPOSITORY_ROOT, REPOSITORY_ROOT / "BertScript"):
            with self.subTest(caller_cwd=caller_cwd):
                result = run_python(
                    f"""
                    import builtins
                    import os
                    import runpy
                    import sys

                    repository_root = {str(REPOSITORY_ROOT)!r}
                    script = {str(SCRIPT)!r}
                    original_cwd = os.getcwd()
                    sys.path = [path for path in sys.path if path != repository_root]
                    original_import = builtins.__import__

                    def checked_import(name, *args, **kwargs):
                        if name == "text_category_profiler.core.utilities":
                            assert repository_root in sys.path
                            assert os.getcwd() == original_cwd
                            print("BOOTSTRAP_OK")
                            raise SystemExit(0)
                        return original_import(name, *args, **kwargs)

                    builtins.__import__ = checked_import
                    runpy.run_path(script, run_name="__main__")
                    raise AssertionError("utilities import was not observed")
                    """,
                    caller_cwd,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("BOOTSTRAP_OK", result.stdout)

    def test_direct_script_generates_tsv_files_relative_to_caller_cwd(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            caller_cwd = Path(temporary_directory)
            label_dir = caller_cwd / "data_set_THUC" / "ExampleLabel"
            label_dir.mkdir(parents=True)
            sample_text = "Hello world\n第二行\u3000" + ("x" * 200)
            (label_dir / "sample.txt").write_text(sample_text, encoding="utf-8")

            result = run_python(
                f"""
                import os
                import runpy
                import sys
                import types

                script = {str(SCRIPT)!r}
                package = types.ModuleType("text_category_profiler")
                package.__path__ = []
                core = types.ModuleType("text_category_profiler.core")
                core.__path__ = []
                utilities = types.ModuleType("text_category_profiler.core.utilities")
                utilities.MKDIR = lambda path: os.makedirs(path, exist_ok=True)
                sys.modules["text_category_profiler"] = package
                sys.modules["text_category_profiler.core"] = core
                sys.modules["text_category_profiler.core.utilities"] = utilities
                runpy.run_path(script, run_name="__main__")
                """,
                caller_cwd,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            output_dir = caller_cwd / "THUC_txt"
            train = output_dir / "train.tsv"
            dev = output_dir / "dev.tsv"
            test = output_dir / "test.tsv"
            self.assertTrue(train.is_file())
            self.assertTrue(dev.is_file())
            self.assertTrue(test.is_file())
            self.assertFalse((REPOSITORY_ROOT / "THUC_txt").exists())

            train_text = train.read_text(encoding="utf-8")
            self.assertTrue(train_text.startswith("ExampleLabel\tHelloworld第二行"))
            self.assertNotIn(" ", train_text)
            self.assertNotIn("\u3000", train_text)
            payload = train_text.rstrip("\n").split("\t", 1)[1]
            self.assertEqual(len(payload), 128)
            self.assertEqual(dev.read_text(encoding="utf-8"), "")
            self.assertEqual(test.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
