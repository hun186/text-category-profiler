"""BL-001 stage-local Excel writer deduplication and API compatibility.

These tests import no models, database or WorkPool. The optional pandas test
checks real XLSX output with both old and new to_excel signatures.
"""
import ast
from pathlib import Path
import tempfile
import unittest
import zipfile

from text_category_profiler.data.stage_xlsx import write_stage_xlsx

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ("DatasetConverter/df_utils.py", "BertScript/df_utils.py")


def isolated_legacy_xls(path):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"), filename=path)
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "dfToXLS"
    ]
    if len(selected) != 1:
        raise AssertionError("Expected exactly one stage-local dfToXLS")
    scope = {}
    exec(compile(ast.Module(body=selected, type_ignores=[]), path, "exec"), scope)
    return scope["dfToXLS"], selected[0]


class RecordingFrame:
    def __init__(self, *, fail=None):
        self.calls = []
        self.fail = fail

    def to_excel(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail:
            raise self.fail


class StageLocalXLSXTests(unittest.TestCase):
    def test_shared_writer_reproduces_exact_legacy_pandas_options(self):
        frame = RecordingFrame()
        self.assertIsNone(write_stage_xlsx(frame, "out.xlsx", excelindex=False))
        self.assertEqual(frame.calls, [
            (("out.xlsx",),
             {"engine": "xlsxwriter", "index": False, "encoding": "utf-8"})
        ])
        self.assertIsNone(write_stage_xlsx(frame, "out2.xlsx"))
        self.assertEqual(frame.calls[1][1]["index"], True)

    def test_old_and_new_to_excel_signatures_and_no_retry(self):
        class LegacyFrame:
            def __init__(self):
                self.calls = []

            def to_excel(self, name, *, engine, index, encoding):
                self.calls.append((name, engine, index, encoding))

        class ModernFrame:
            def __init__(self):
                self.calls = []

            def to_excel(self, name, *, engine, index):
                self.calls.append((name, engine, index))

        class FailingModernFrame(ModernFrame):
            def to_excel(self, name, *, engine, index):
                self.calls.append((name, engine, index))
                raise RuntimeError("write failed after starting")

        for path in PROVIDERS:
            with self.subTest(provider=path):
                fn, _ = isolated_legacy_xls(path)
                legacy = LegacyFrame()
                modern = ModernFrame()
                self.assertIsNone(fn(legacy, "old.xlsx", excelindex=False))
                self.assertIsNone(fn(modern, "new.xlsx", excelindex=False))
                self.assertEqual(
                    legacy.calls, [("old.xlsx", "xlsxwriter", False, "utf-8")]
                )
                self.assertEqual(
                    modern.calls, [("new.xlsx", "xlsxwriter", False)]
                )
                failing = FailingModernFrame()
                with self.assertRaisesRegex(RuntimeError, "write failed after starting"):
                    fn(failing, "failure.xlsx")
                self.assertEqual(
                    failing.calls, [("failure.xlsx", "xlsxwriter", True)]
                )

    def test_both_existing_stage_apis_reexport_via_explicit_single_provider(self):
        for path in PROVIDERS:
            with self.subTest(path=path):
                fn, node = isolated_legacy_xls(path)
                provider_imports = [
                    n for n in ast.walk(node)
                    if isinstance(n, ast.ImportFrom)
                    and n.module == "text_category_profiler.data.stage_xlsx"
                ]
                self.assertEqual(len(provider_imports), 1)
                self.assertEqual(
                    [x.name for x in provider_imports[0].names],
                    ["write_stage_xlsx"],
                )
                self.assertFalse(any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "to_excel"
                    for n in ast.walk(node)
                ))
                frame = RecordingFrame()
                self.assertIsNone(
                    fn(frame, "legacy.xlsx", excelindex=False, encoding="big5")
                )
                self.assertEqual(frame.calls, [
                    (("legacy.xlsx",), {
                        "engine": "xlsxwriter",
                        "index": False,
                        "encoding": "utf-8",
                    })
                ])
                with self.assertRaises(TypeError):
                    fn(frame, "file.xlsx", sheet_name="custom")

    def test_legacy_writer_failure_propagates_without_fallback_or_retry(self):
        error = RuntimeError("simulated Excel failure")
        for path in PROVIDERS:
            with self.subTest(path=path):
                fn, _ = isolated_legacy_xls(path)
                frame = RecordingFrame(fail=error)
                with self.assertRaises(RuntimeError) as result:
                    fn(frame, "failed.xlsx")
                self.assertIs(result.exception, error)
                self.assertEqual(len(frame.calls), 1)

    def test_new_shared_module_has_no_heavy_or_service_import(self):
        source = (
            ROOT / "text_category_profiler/data/stage_xlsx.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = [
            node for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        self.assertEqual(len(imports), 1)
        self.assertIsInstance(imports[0], ast.ImportFrom)
        self.assertEqual(imports[0].module, "inspect")
        self.assertEqual(
            [item.name for item in imports[0].names],
            ["Parameter", "signature"],
        )

    def test_optional_real_pandas_outputs_semantically_equivalent_xlsx(self):
        try:
            import pandas as pd
            import xlsxwriter  # noqa: F401; required by the fixed stage engine
        except ImportError:
            self.skipTest("pandas/xlsxwriter not installed for real-I/O check")
        data = pd.DataFrame({"label": ["TW Affairs", "TW Security"],
                             "content": ["中文分類", "先進製程"]})
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "baseline.xlsx"
            # The reference call uses the API actually supported by this
            # installed pandas; the stage writer must produce the same cells.
            from inspect import signature
            options = {"engine": "xlsxwriter", "index": False}
            if "encoding" in signature(data.to_excel).parameters:
                options["encoding"] = "utf-8"
            data.to_excel(base, **options)

            for i, provider in enumerate(PROVIDERS):
                with self.subTest(provider=provider):
                    fn, _ = isolated_legacy_xls(provider)
                    path = Path(temp) / f"stage{i}.xlsx"
                    self.assertIsNone(fn(data, path, excelindex=False))
                    self.assertTrue(zipfile.is_zipfile(path))
                    # ZIP metadata can differ; compare actual workbook content.
                    with zipfile.ZipFile(base) as baseline, zipfile.ZipFile(path) as produced:
                        for name in (
                            "xl/worksheets/sheet1.xml",
                            "xl/sharedStrings.xml",
                        ):
                            if name in baseline.namelist():
                                self.assertEqual(
                                    baseline.read(name), produced.read(name)
                                )


if __name__ == "__main__":
    unittest.main()
