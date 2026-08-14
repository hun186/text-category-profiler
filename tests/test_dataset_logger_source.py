import ast
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from DatasetConverter.logger_source import create_sample_reader_logger


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DatasetLoggerSourceTests(unittest.TestCase):
    def test_factory_preserves_legacy_logger_constructor_contract(self):
        calls = []
        expected_logger = object()
        fake_mp_utils = types.ModuleType(
            "text_category_profiler.concurrency.MP_utils"
        )

        def fake_logger(**kwargs):
            calls.append(kwargs)
            return expected_logger

        fake_mp_utils.MPlogger = fake_logger
        with patch.dict(
            sys.modules,
            {"text_category_profiler.concurrency.MP_utils": fake_mp_utils},
        ):
            result = create_sample_reader_logger(log_file="reader.log")

        self.assertIs(result, expected_logger)
        self.assertEqual(calls, [{"logFile": "reader.log"}])

    def test_reader_does_not_import_mp_utils_at_module_scope(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("text_category_profiler.concurrency.MP_utils", imports)

    def test_logger_adapter_imports_mp_utils_only_inside_factory(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "logger_source.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module_imports = [
            node.module
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        ]
        self.assertNotIn("text_category_profiler.concurrency.MP_utils", module_imports)

    def test_reader_import_no_longer_requires_numpy_from_mp_utils(self):
        script = """
import os
import sys

before = os.getcwd()
import DatasetConverter.sampleHandler
assert os.getcwd() == before
assert 'text_category_profiler.concurrency.MP_utils' not in sys.modules
assert 'text_category_profiler.text.TextProcessor_utils' not in sys.modules
assert 'ClassesTree.Label_utils' not in sys.modules
"""
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
