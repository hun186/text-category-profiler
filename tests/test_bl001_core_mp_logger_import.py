"""Protect the shared core MPlogger provider boundary without importing heavy dependencies."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "text_category_profiler" / "core" / "utilities.py"
CONCURRENCY = ROOT / "text_category_profiler" / "concurrency" / "MP_utils.py"
PROVIDER = "text_category_profiler.concurrency.MP_utils"


def tree(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class CoreMPLoggerImportTests(unittest.TestCase):
    def test_only_one_canonical_mp_logger_import_exists(self):
        source = tree(CORE)
        imports = [
            item for item in ast.walk(source)
            if isinstance(item, ast.ImportFrom)
            and any(alias.name == "MPlogger" for alias in item.names)
        ]
        self.assertEqual(len(imports), 1)
        self.assertEqual(imports[0].module, PROVIDER)
        self.assertEqual(imports[0].level, 0)
        self.assertIsInstance(
            next(node for node in source.body if node is imports[0]),
            ast.ImportFrom,
        )
        self.assertFalse(any(
            isinstance(item, ast.ImportFrom) and item.module == "MP_utils"
            for item in ast.walk(source)
        ))

    def test_canonical_mp_logger_provider_has_instance_based_api(self):
        classes = [
            item for item in tree(CONCURRENCY).body
            if isinstance(item, ast.ClassDef) and item.name == "MPlogger"
        ]
        self.assertEqual(len(classes), 1)
        methods = {
            item.name: item for item in classes[0].body
            if isinstance(item, ast.FunctionDef)
        }
        self.assertIn("__init__", methods)
        self.assertIn("logW", methods)
        self.assertEqual(methods["logW"].args.args[0].arg, "self")
        self.assertEqual(methods["__init__"].args.args[0].arg, "self")

    def test_canonical_provider_failure_is_not_masked_by_relative_fallback(self):
        source = tree(CORE)
        statement = next(
            item for item in source.body
            if isinstance(item, ast.ImportFrom) and item.module == PROVIDER
            and any(alias.name == "MPlogger" for alias in item.names)
        )
        calls = []

        def fail_import(name, *args, **kwargs):
            calls.append(name)
            raise RuntimeError("true concurrency import failure")

        with patch("builtins.__import__", side_effect=fail_import):
            with self.assertRaisesRegex(RuntimeError, "true concurrency import failure"):
                exec(compile(ast.Module(body=[statement], type_ignores=[]), str(CORE), "exec"), {})
        self.assertEqual(calls, [PROVIDER])


if __name__ == "__main__":
    unittest.main()
