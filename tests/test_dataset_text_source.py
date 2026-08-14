import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from DatasetConverter.text_source import clean_text_with_patterns
from DatasetConverter.text_source import normalize_basic_text
from DatasetConverter.text_source import read_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_NAME = "text_category_profiler.text.TextProcessor_utils"


class DatasetTextSourceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        calls = self.calls
        fake_module = types.ModuleType(MODULE_NAME)

        class FakeReader:
            def __init__(self, **kwargs):
                calls.append(("reader", kwargs))

            def run(self):
                return "read result"

        class FakeBasicCleaner:
            def __init__(self, **kwargs):
                calls.append(("basic", kwargs))

            def proc(self, text):
                calls.append(("basic.proc", text))
                return "normalized result"

        class FakePatternCleaner:
            def __init__(self, text, **kwargs):
                calls.append(("pattern", text, kwargs))

            def proc(self):
                return "cleaned result"

        fake_module.textReader = FakeReader
        fake_module.BasicDataCleaner = FakeBasicCleaner
        fake_module.DataCleanerWithPattern = FakePatternCleaner
        self.module_patch = patch.dict(sys.modules, {MODULE_NAME: fake_module})
        self.module_patch.start()

    def tearDown(self):
        self.module_patch.stop()

    def test_read_text_preserves_legacy_arguments(self):
        logger = object()
        result = read_text(
            file="fixture.ai2",
            encoding="cp950",
            n_bytes=12,
            logger=logger,
        )
        self.assertEqual(result, "read result")
        self.assertEqual(
            self.calls,
            [
                (
                    "reader",
                    {
                        "file": "fixture.ai2",
                        "encoding": "cp950",
                        "nBytes": 12,
                        "MPLOGGER": logger,
                    },
                )
            ],
        )

    def test_basic_normalizer_preserves_legacy_arguments(self):
        result = normalize_basic_text(
            "fixture", convert_full_width=False, dummy_space=True
        )
        self.assertEqual(result, "normalized result")
        self.assertEqual(
            self.calls,
            [
                ("basic", {"strQ2B": False, "DummySpace": True}),
                ("basic.proc", "fixture"),
            ],
        )

    def test_pattern_cleaner_preserves_legacy_arguments(self):
        logger = object()
        rules = {"mail": {"SrcPat": "x", "ReplacedResult": ""}}
        result = clean_text_with_patterns(
            "fixture", rules, logger=logger, print_on_screen=True
        )
        self.assertEqual(result, "cleaned result")
        self.assertEqual(
            self.calls,
            [
                (
                    "pattern",
                    "fixture",
                    {
                        "RePatternDict": rules,
                        "MPLOGGER": logger,
                        "printOnScreen": True,
                    },
                )
            ],
        )

    def test_reader_and_adapter_have_no_module_scope_legacy_import(self):
        for relative_path in (
            "DatasetConverter/sampleHandler.py",
            "DatasetConverter/text_source.py",
        ):
            tree = ast.parse(
                (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
            )
            module_imports = [
                node.module
                for node in tree.body
                if isinstance(node, ast.ImportFrom)
            ]
            self.assertNotIn(MODULE_NAME, module_imports, relative_path)


if __name__ == "__main__":
    unittest.main()
