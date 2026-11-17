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
