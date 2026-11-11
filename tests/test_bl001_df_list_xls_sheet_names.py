"""BL-001: canonical multi-sheet Excel must not consume caller sheet names.

Function-level AST injection avoids import-time GPUtil, ML runtimes or WorkPool.
Optional pandas/xlsxwriter integration writes exclusively to a private tempfile.
"""
import ast
from pathlib import Path
import tempfile
import unittest
import warnings
import xml.etree.ElementTree as ET
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "text_category_profiler/data/df_utils.py"


def isolated_export(pd):
    tree = ast.parse(PROVIDER.read_text(encoding="utf-8-sig"), filename=str(PROVIDER))
    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "dfListToXLS"
    ]
    if len(selected) != 1:
        raise AssertionError("Canonical multi-sheet XLSX exporter must exist")
    scope = {"pd": pd}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(PROVIDER), "exec"), scope)
    return scope["dfListToXLS"]


class FakeBook:
    def add_format(self):
        class Format:
            def set_align(self, alignment):
                assert alignment == "vcenter"
        return Format()


class FakeSheet:
    def __init__(self):
        self.row_heights = []

    def set_row(self, row, height):
        self.row_heights.append((row, height))


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
        writer.sheets[sheet_name] = FakeSheet()


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

    def test_row_height_uses_non_inplace_reset_and_keeps_original(self):
        class RangeIndex:
            start = 0
            step = 1

        class HeightPandas(FakePandas):
            pass

        HeightPandas.RangeIndex = RangeIndex

        class FakeRow:
            def apply(self, function):
                class Calculated:
                    name = "0"
                    def max(self):
                        return max(function("one\ntwo"), function("three"))
                return Calculated()

        class HeightFrame(FakeFrame):
            def __init__(self, reset=False):
                super().__init__()
                self.index = RangeIndex()
                self.was_reset = reset
                self.reset_calls = []
                self.iterated = False

            def reset_index(self, *, drop=False):
                self.reset_calls.append(drop)
                return HeightFrame(reset=True)

            def iterrows(self):
                self.iterated = True
                if not self.was_reset:
                    raise AssertionError("Must not iterate original frame")
                yield 0, FakeRow()

        pd = HeightPandas()
        export = isolated_export(pd)
        frame = HeightFrame()
        export([frame], "private.xlsx", sheetNameList=["Rows"],
               AutoAdjustRowWidth=True)
        self.assertEqual(frame.reset_calls, [True])
        self.assertFalse(frame.was_reset)
        self.assertFalse(frame.iterated)
        self.assertEqual(pd.writers[0].sheets["Rows"].row_heights, [(1, 24)])

    def test_real_pandas_row_height_does_not_change_dataframe(self):
        try:
            import pandas as pd
            import xlsxwriter  # noqa: F401
        except ImportError:
            self.skipTest("Optional pandas/xlsxwriter not installed")
        export = isolated_export(pd)
        with tempfile.TemporaryDirectory(prefix="bl001-row-height-") as folder:
            for case, index in (
                ("range", pd.RangeIndex(start=0, stop=2)),
                ("named", pd.Index(["row\n1", "row2"], name="source")),
            ):
                with self.subTest(index=case):
                    source = pd.DataFrame(
                        {"text": ["台北\n桃園", "新竹"], "label": ["A", "B"]},
                        index=index,
                    )
                    before = source.copy(deep=True)
                    output = Path(folder) / f"{case}.xlsx"
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")
                        export([source], output, sheetNameList=["結果"],
                               AutoAdjustRowWidth=True, excelindex=False)
                    pd.testing.assert_frame_equal(source, before)
                    self.assertTrue(zipfile.is_zipfile(output))
                    with zipfile.ZipFile(output) as workbook:
                        sheet_xml = ET.fromstring(
                            workbook.read("xl/worksheets/sheet1.xml")
                        )
                        rows = sheet_xml.findall(
                            ".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"
                        )
                        self.assertTrue(
                            any(row.attrib.get("customHeight") == "1" for row in rows),
                            "Row-height formatting should still be applied",
                        )

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
