"""BL-001 no-service characterization of three dfToXLS export contracts.

Execute only selected function ASTs against in-memory stand-ins, not entire
provider modules. No pandas/Excel, optional dependencies or WorkPool are loaded.
"""
import ast
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY = (
    "DatasetConverter/df_utils.py",
    "BertScript/df_utils.py",
)
CANONICAL = "text_category_profiler/data/df_utils.py"


def isolated_xls_function(path, **dependencies):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"), filename=path)
    definitions = [
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "dfToXLS"
    ]
    if len(definitions) != 1:
        raise AssertionError(f"Expected exactly one dfToXLS in {path}")
    scope = dict(dependencies)
    exec(
        compile(ast.Module(body=definitions, type_ignores=[]), path, "exec"),
        scope,
    )
    return scope["dfToXLS"]


class RecordingFrame:
    def __init__(self, rows=2):
        self.shape = (rows, 2)
        self.calls = []

    def to_excel(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class RecordingWriter:
    def __init__(self):
        self.entered = False
        self.exited = False

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exited = True
        return False


class RecordingPandas:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []
        self.writer = RecordingWriter()

    def ExcelWriter(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.fail:
            raise RuntimeError("injected writer unavailable")
        return self.writer


class XlsProviderContractTests(unittest.TestCase):
    def test_legacy_stage_exports_share_static_xlsxwriter_call(self):
        observed = []
        for provider in LEGACY:
            with self.subTest(provider=provider):
                frame = RecordingFrame()
                fn = isolated_xls_function(provider)
                self.assertIsNone(fn(frame, "file.xlsx", excelindex=False, encoding="big5"))
                self.assertEqual(len(frame.calls), 1)
                observed.append(frame.calls[0])
                with self.assertRaises(TypeError):
                    fn(frame, "file.xlsx", sheet_name="Custom")
        self.assertEqual(observed[0], observed[1])
        self.assertEqual(observed[0], (
            ("file.xlsx",),
            {"engine": "xlsxwriter", "index": False, "encoding": "utf-8"},
        ))

    def test_canonical_uses_explicit_writer_and_worksheet_contract(self):
        pd = RecordingPandas()
        frame = RecordingFrame()
        fn = isolated_xls_function(CANONICAL, pd=pd)
        self.assertIsNone(
            fn(frame, "file.xlsx", excelindex=False, sheet_name="MySheet", mode="w")
        )
        self.assertEqual(pd.calls, [(
            ("file.xlsx",),
            {"engine": "xlsxwriter", "engine_kwargs": {
                "options": {"strings_to_urls": False}}, "mode": "w"},
        )])
        self.assertEqual(frame.calls, [(
            (pd.writer,), {"index": False, "sheet_name": "MySheet"},
        )])
        self.assertTrue(pd.writer.entered)
        self.assertTrue(pd.writer.exited)
        with self.assertRaises(TypeError):
            fn(frame, "file.xlsx", encoding="utf-8")

    def test_canonical_row_limit_skips_writer_while_legacy_does_not_precheck(self):
        pd = RecordingPandas()
        canonical = isolated_xls_function(CANONICAL, pd=pd)
        within = RecordingFrame(rows=1048576)
        canonical(within, "limit.xlsx")
        self.assertEqual(len(pd.calls), 1)
        above = RecordingFrame(rows=1048577)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertIsNone(canonical(above, "overflow.xlsx"))
        self.assertEqual(len(pd.calls), 1)
        self.assertEqual(above.calls, [])
        self.assertIn("1048576", stdout.getvalue())

        for provider in LEGACY:
            frame = RecordingFrame(rows=1048577)
            isolated_xls_function(provider)(frame, "overflow.xlsx")
            self.assertEqual(len(frame.calls), 1)
        # Mock call presence is not proof that a real Excel writer accepts overflow.

    def test_canonical_writer_failure_falls_back_to_direct_to_excel(self):
        pd = RecordingPandas(fail=True)
        frame = RecordingFrame()
        fn = isolated_xls_function(CANONICAL, pd=pd)
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            self.assertIsNone(fn(frame, "fallback.xlsx", excelindex=False, sheet_name="Alt"))
        self.assertEqual(len(pd.calls), 1)
        self.assertEqual(frame.calls, [(
            ("fallback.xlsx",), {"index": False, "sheet_name": "Alt"},
        )])
        self.assertIn("injected writer unavailable", stdout.getvalue())
        # This preserves an existing broad fallback; no claim of write success.


if __name__ == "__main__":
    unittest.main()
