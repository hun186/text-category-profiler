"""BL-001: the two stage-local TSV APIs share one unchanged formatter.

Only bounded in-memory recorder tests execute the stage functions; production
pandas, multiprocessing, WorkPool and model imports are not required.
"""
from __future__ import annotations

import ast
import csv
import io
from pathlib import Path
import tempfile
import unittest

from text_category_profiler.data.stage_tsv import write_stage_tsv

ROOT = Path(__file__).resolve().parents[1]
STAGE_PROVIDERS = (
    "DatasetConverter/df_utils.py",
    "BertScript/df_utils.py",
)


def isolated_legacy_tsv(path):
    source = (ROOT / path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=path)
    functions = [node for node in tree.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "dfToTSV"]
    if len(functions) != 1:
        raise AssertionError("Expected exactly one legacy dfToTSV: " + path)
    scope = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), path, "exec"), scope)
    return scope["dfToTSV"], functions[0]


class RecordingFrame:
    def __init__(self, *, failure=None):
        self.calls = []
        self.failure = failure

    def to_csv(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.failure:
            raise self.failure


class SharedStageTSVTests(unittest.TestCase):
    def test_format_policy_is_the_original_fixed_stage_contract(self):
        frame = RecordingFrame()
        self.assertIsNone(write_stage_tsv(frame, "output.tsv"))
        self.assertEqual(frame.calls, [
            (("output.tsv",), {
                "sep": "\t", "index": False,
                "quoting": csv.QUOTE_NONE, "quotechar": "",
                "escapechar": "\\", "header": False,
                "encoding": "utf-8",
            })
        ])

    def test_both_two_arg_legacy_apis_delegate_to_exactly_one_shared_provider(self):
        for provider in STAGE_PROVIDERS:
            with self.subTest(provider=provider):
                function, node = isolated_legacy_tsv(provider)
                scoped_imports = [
                    child for child in ast.walk(node)
                    if isinstance(child, ast.ImportFrom)
                    and child.module == "text_category_profiler.data.stage_tsv"
                ]
                self.assertEqual(len(scoped_imports), 1)
                self.assertEqual(
                    [alias.name for alias in scoped_imports[0].names],
                    ["write_stage_tsv"],
                )
                frame = RecordingFrame()
                self.assertIsNone(function(frame, "legacy.tsv"))
                self.assertEqual(len(frame.calls), 1)
                self.assertEqual(
                    frame.calls[0][1]["quoting"], csv.QUOTE_NONE,
                )
                with self.assertRaises(TypeError):
                    function(frame, "legacy.tsv", header=True)

    def test_write_failure_is_preserved_and_not_swallowed(self):
        error = RuntimeError("injected output write failure")
        for provider in STAGE_PROVIDERS:
            with self.subTest(provider=provider):
                frame = RecordingFrame(failure=error)
                function, _ = isolated_legacy_tsv(provider)
                with self.assertRaises(RuntimeError) as caught:
                    function(frame, "unwritable.tsv")
                self.assertIs(caught.exception, error)
                self.assertEqual(len(frame.calls), 1)

    def test_shared_module_is_dependency_light_without_optional_imports(self):
        source = (ROOT / "text_category_profiler/data/stage_tsv.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imports = [
            alias.name for node in tree.body if isinstance(node, ast.Import)
            for alias in node.names
        ]
        self.assertEqual(imports, ["csv"])
        self.assertFalse(any(isinstance(node, ast.ImportFrom) for node in tree.body))

    def test_real_pandas_export_is_identical_to_original_options_if_installed(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas is optional for dependency-light tests")
        data = pd.DataFrame([
            ["TW Affairs", "包含製表符\t與反斜線\\字元", 1],
            ["TW Security", "中文分類、換行\n仍使用既有 TSV escape", 2],
        ], columns=["ClassLabel", "text", "Score"])
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "expected.tsv"
            legacy_error = None
            try:
                data.to_csv(
                    target, sep="\t", index=False, quoting=csv.QUOTE_NONE,
                    quotechar="", escapechar="\\", header=False,
                    encoding="utf-8",
                )
            except (TypeError, ValueError) as error:
                # Pandas 3.x can reject the historical empty quotechar.
                # This refactor must preserve that exception, not conceal it.
                legacy_error = error
            for provider in STAGE_PROVIDERS:
                with self.subTest(provider=provider):
                    function, _ = isolated_legacy_tsv(provider)
                    actual_path = Path(tmp) / provider.replace("/", "_")
                    if legacy_error is not None:
                        with self.assertRaises(type(legacy_error)) as caught:
                            function(data, actual_path)
                        self.assertEqual(str(caught.exception), str(legacy_error))
                    else:
                        function(data, actual_path)
                        self.assertEqual(actual_path.read_bytes(), target.read_bytes())


if __name__ == "__main__":
    unittest.main()
