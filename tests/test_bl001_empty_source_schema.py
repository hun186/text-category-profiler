"""Canonical empty-source handoff regression: real SQLite Src index, no fake rows."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd

from DatasetConverter.core.sample_schema import (
    SAMPLE_ROW_COLUMNS, preserve_empty_source_metadata_schema,
)
from text_category_profiler.data.canonical_sql_atomic import replace_canonical_table


class EmptySourceSchemaTests(unittest.TestCase):
    def test_zero_regular_sources_gain_only_missing_provenance_columns(self):
        frame = pd.DataFrame(columns=SAMPLE_ROW_COLUMNS)
        actual = preserve_empty_source_metadata_schema(frame)
        self.assertIs(actual, frame)
        self.assertEqual(frame.shape, (0, 7))
        self.assertEqual(
            frame.columns.tolist(),
            [*SAMPLE_ROW_COLUMNS, "SrcType", "Src"],
        )
        self.assertEqual(str(frame["Src"].dtype), "object")
        self.assertEqual(str(frame["SrcType"].dtype), "object")
        preserve_empty_source_metadata_schema(frame)
        self.assertEqual(frame.shape, (0, 7))

    def test_zero_column_optional_fixed_test_and_es_export_real_indexes(self):
        """Both optional no-input outputs previously began as 0x0 frames."""
        for source in ("fixed_test_disabled", "elasticsearch_disabled"):
            with self.subTest(source=source):
                frame = pd.DataFrame()
                self.assertEqual(frame.shape, (0, 0))
                self.assertIs(preserve_empty_source_metadata_schema(frame), frame)
                self.assertEqual(
                    frame.columns.tolist(),
                    [*SAMPLE_ROW_COLUMNS, "SrcType", "Src"],
                )
                self.assertTrue(all(str(dtype) == "object"
                                    for dtype in frame.dtypes))
                preserve_empty_source_metadata_schema(frame)
                self.assertEqual(frame.shape, (0, 7))
                with tempfile.TemporaryDirectory(prefix="bl001-empty-optional-") as tmp:
                    db_path = Path(tmp) / "optional.sqlite3"
                    with closing(sqlite3.connect(db_path)) as cnx:
                        replace_canonical_table(
                            cnx, frame, table="sampleSrc", dtype=None,
                            index_label=None, index_cols=["text", "Src"],
                        )
                    with closing(sqlite3.connect(db_path)) as cnx:
                        self.assertEqual(
                            cnx.execute('SELECT COUNT(*) FROM "sampleSrc"').fetchone(),
                            (0,),
                        )
                        self.assertEqual(
                            [row[1] for row in cnx.execute('PRAGMA table_info("sampleSrc")')],
                            ["index", *SAMPLE_ROW_COLUMNS, "SrcType", "Src"],
                        )
                        indexes = {
                            item[1] for item in cnx.execute('PRAGMA index_list("sampleSrc")')
                        }
                        self.assertEqual(
                            indexes, {"ix_sampleSrc_index", "text_Index", "Src_Index"},
                        )
                        for name, column in (("text_Index", "text"), ("Src_Index", "Src")):
                            keys = [
                                row for row in cnx.execute(
                                    'PRAGMA index_xinfo("' + name + '")'
                                ) if row[5] == 1
                            ]
                            self.assertEqual(len(keys), 1)
                            self.assertGreaterEqual(keys[0][1], 0)
                            self.assertEqual(keys[0][2], column)
                        self.assertEqual(
                            cnx.execute("PRAGMA quick_check(1)").fetchone(), ("ok",)
                        )

    def test_partial_empty_frame_preserves_existing_values_and_dtype(self):
        frame = pd.DataFrame({
            "text": pd.Series(dtype="string"),
            "OutLabel": pd.Series(dtype="category"),
        })
        preserve_empty_source_metadata_schema(frame)
        self.assertEqual(frame.shape, (0, 7))
        self.assertEqual(str(frame["text"].dtype), "string")
        self.assertEqual(str(frame["OutLabel"].dtype), "category")
        self.assertEqual(frame.columns[:2].tolist(), ["text", "OutLabel"])

    def test_dataconverter_normalizes_optional_outputs_before_sql_export(self):
        """The DataConverter integration must use the policy in both branches."""
        import ast

        root = Path(__file__).resolve().parents[1]
        module = ast.parse(
            (root / "DatasetConverter" / "DataConverter.py").read_text(encoding="utf-8")
        )
        cls = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "DatasetGenerator"
        )
        run = next(
            node for node in cls.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        all_calls = [
            call for call in ast.walk(run) if isinstance(call, ast.Call)
        ]
        def index_of_normalization(name):
            matches = [
                node for node in ast.walk(run)
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "preserve_empty_source_metadata_schema"
                and len(node.value.args) == 1
                and isinstance(node.value.args[0], ast.Name)
                and node.value.args[0].id == name
            ]
            self.assertEqual(len(matches), 1, name)
            return matches[0].lineno

        for variable, attr in (("FT_df", "OUTPUTMAIN_FT"), ("es_df", "OUTPUTMAIN_es")):
            with self.subTest(branch=variable):
                normalized_line = index_of_normalization(variable)
                exports = [
                    call for call in all_calls
                    if isinstance(call.func, ast.Name)
                    and call.func.id == "dfOutputer"
                    and len(call.args) >= 2
                    and isinstance(call.args[0], ast.Name)
                    and call.args[0].id == variable
                    and isinstance(call.args[1], ast.Attribute)
                    and call.args[1].attr == attr
                ]
                self.assertEqual(len(exports), 1)
                self.assertLess(normalized_line, exports[0].lineno)

    def test_nonempty_sample_missing_src_is_not_silently_forgiven(self):
        frame = pd.DataFrame([{
            "file": "sample.txt", "InLabel": "TW Affairs",
            "OutLabel": "TW Affairs", "text": "hello", "PartNO": 0,
        }])
        result = preserve_empty_source_metadata_schema(frame)
        self.assertIs(result, frame)
        self.assertNotIn("Src", frame)
        with tempfile.TemporaryDirectory(prefix="bl001-empty-src-") as root:
            db_path = Path(root) / "private.sqlite3"
            with closing(sqlite3.connect(db_path)) as db:
                with self.assertRaisesRegex(ValueError, "Requested index column absent: Src"):
                    replace_canonical_table(
                        db, frame, table="sampleSrc", dtype=None,
                        index_label=None, index_cols=["text", "Src"],
                    )
            with closing(sqlite3.connect(db_path)) as db:
                self.assertFalse(db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sampleSrc'"
                ).fetchone())

    def test_empty_canonical_total_has_real_src_and_text_indexes(self):
        frame = preserve_empty_source_metadata_schema(
            pd.DataFrame(columns=SAMPLE_ROW_COLUMNS)
        )
        with tempfile.TemporaryDirectory(prefix="bl001-empty-src-") as root:
            db_path = Path(root) / "private.sqlite3"
            with closing(sqlite3.connect(db_path)) as db:
                replace_canonical_table(
                    db, frame, table="sampleSrc", dtype=None,
                    index_label=None, index_cols=["text", "Src"],
                )
            with closing(sqlite3.connect(db_path)) as db:
                self.assertEqual(
                    db.execute('SELECT COUNT(*) FROM "sampleSrc"').fetchone(),
                    (0,),
                )
                actual_columns = [
                    row[1] for row in db.execute('PRAGMA table_info("sampleSrc")')
                ]
                self.assertEqual(
                    actual_columns,
                    ["index", *SAMPLE_ROW_COLUMNS, "SrcType", "Src"],
                )
                actual_indexes = {
                    row[1] for row in db.execute('PRAGMA index_list("sampleSrc")')
                }
                self.assertEqual(
                    actual_indexes, {"ix_sampleSrc_index", "text_Index", "Src_Index"},
                )
                for index_name, expected_column in (
                    ("text_Index", "text"), ("Src_Index", "Src"),
                ):
                    keys = [
                        row for row in db.execute('PRAGMA index_xinfo("' + index_name + '")')
                        if row[5] == 1
                    ]
                    self.assertEqual(len(keys), 1)
                    self.assertGreaterEqual(keys[0][1], 0)
                    self.assertEqual(keys[0][2], expected_column)
                    self.assertEqual(keys[0][4], "BINARY")
                self.assertEqual(db.execute("PRAGMA quick_check(1)").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
