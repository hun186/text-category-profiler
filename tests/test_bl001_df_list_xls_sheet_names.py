"""BL-001: canonical multi-sheet Excel must not consume caller sheet names.

Function-level AST injection avoids import-time GPUtil, ML runtimes or WorkPool.
Optional pandas/xlsxwriter integration writes exclusively to a private tempfile.
"""
import ast
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "text_category_profiler/data/df_utils.py"


def isolated_export(pd):
    tree = ast.parse(PROVIDER.read_text(encoding="utf-8-sig"), filename=str(PROVIDER))
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "dfListToXLS"
    ]
    if len(matches) != 1:
        raise AssertionError("Canonical dfListToXLS was not found exactly once")
    scope = {"pd": pd}
    exec(compile(ast.Module(body=matches, type_ignores=[]), str(PROVIDER), "exec"), scope)
    return scope["dfListToXLS"]


class FakeBook:
    def add_format(self):
        class Format:
            def set_align(self, alignment):
                assert alignment == "vcenter"
        return Format()


class FakeWriter:
    def __init__(self):
        self.book = FakeBook()
        self.sheets = {}
        self.names = []
        self.closed = 0

    def close(self):
        self.closed += 1


class FakePandas:
    def __init__(self):
        self.writers = []
        self.arguments = []

    def ExcelWriter(self, *args, **kwargs):
        self.arguments.append((args, kwargs))
        writer = FakeWriter()
        self.writers.append(writer)
        return writer


class FakeFrame:
    shape = (1, 2)

    def __init__(self):
        self.calls = []

    def to_excel(self, writer, *, index, sheet_name):
        self.calls.append((writer, index, sheet_name))
        writer.names.append(sheet_name)
        writer.sheets[sheet_name] = object()


class CanonicalMultiSheetExcelTests(unittest.TestCase):
    def test_names_remain_unchanged_and_reusable_in_order(self):
        pd = FakePandas()
        export = isolated_export(pd)
        names = ["中文第一頁", "Second Page", "Third Page"]
        original = names[:]
        for iteration in range(2):
            frames = [FakeFrame(), FakeFrame(), FakeFrame()]
            self.assertIsNone(export(frames, "private.xlsx", sheetNameList=names))
            self.assertEqual(names, original, "Caller list must not be consumed")
            writer = pd.writers[iteration]
            self.assertEqual(writer.names, original)
            self.assertEqual(writer.closed, 1)
            self.assertTrue(all(len(frame.calls) == 1 for frame in frames))
        self.assertEqual(pd.arguments[0], (
            ("private.xlsx",),
            {"engine": "xlsxwriter", "engine_kwargs": {
                "options": {"strings_to_urls": False}}},
        ))

    def test_extra_frames_keep_existing_auto_sheet_fallback(self):
        pd = FakePandas()
        export = isolated_export(pd)
        names = ["命名頁"]
        export([FakeFrame(), FakeFrame(), FakeFrame()], "private.xlsx",
               sheetNameList=names)
        self.assertEqual(pd.writers[0].names, [
            "命名頁", "AutoSheetName1", "AutoSheetName2",
        ])
        self.assertEqual(names, ["命名頁"])

    def test_empty_default_names_do_not_leak_between_calls(self):
        pd = FakePandas()
        export = isolated_export(pd)
        export([FakeFrame(), FakeFrame()], "private.xlsx")
        export([FakeFrame()], "private2.xlsx")
        self.assertEqual(pd.writers[0].names, ["AutoSheetName1", "AutoSheetName2"])
        self.assertEqual(pd.writers[1].names, ["AutoSheetName1"])

    def test_failed_export_cannot_mutate_caller_names(self):
        pd = FakePandas()
        export = isolated_export(pd)
        names = ["First", "Second"]

        class FailingFrame(FakeFrame):
            def to_excel(self, writer, *, index, sheet_name):
                raise RuntimeError("simulated XLSX export failed")

        with self.assertRaisesRegex(RuntimeError, "simulated XLSX"):
            export([FailingFrame()], "failed.xlsx", sheetNameList=names)
        self.assertEqual(names, ["First", "Second"])

    def test_private_real_xlsx_repeated_exports_have_same_sheet_names(self):
        try:
            import pandas as pd
            import xlsxwriter  # noqa: F401
        except ImportError:
            self.skipTest("Optional pandas/xlsxwriter not installed")
        export = isolated_export(pd)
        names = ["中文分類", "Predictions"]
        frames = [
            pd.DataFrame({"text": ["台北", "桃園"]}),
            pd.DataFrame({"score": [1, 2]}),
        ]
        with tempfile.TemporaryDirectory(prefix="bl001-multi-xlsx-") as folder:
            for iteration in range(2):
                output = Path(folder) / f"export-{iteration}.xlsx"
                export(frames, output, sheetNameList=names)
                self.assertEqual(names, ["中文分類", "Predictions"])
                self.assertTrue(zipfile.is_zipfile(output))
                with zipfile.ZipFile(output) as workbook:
                    xml = ET.fromstring(workbook.read("xl/workbook.xml"))
                    actual = [
                        item.attrib["name"]
                        for item in xml.findall(
                            ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"
                        )
                    ]
                    self.assertEqual(actual, names)


if __name__ == "__main__":
    unittest.main()
