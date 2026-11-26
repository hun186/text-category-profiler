"""Score-range regression fixtures; no real GUI or production database."""
import ast
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from BertScript.visualization_score_reads import read_score_range


class ScoreRangeReadTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "評分 # 1.sql3"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE sampleSrc (File TEXT, InfoScoreSum REAL, text TEXT)")
            conn.executemany("INSERT INTO sampleSrc VALUES (?, ?, ?)", [
                ("zero", 0, "a"), ("low", 1.5, "b"), ("high", 3, "c"),
                ("outside", 4, "d"), ("missing", None, "e"), ("high", 3, "c"),
            ])
            conn.execute("CREATE TABLE unrelated (InfoScoreSum REAL)")
            conn.execute("INSERT INTO unrelated VALUES (2)")

    @staticmethod
    def fetch(query, connection, *, params):
        return connection.execute(query, params).fetchall()

    def read(self, lower, upper):
        return read_score_range(self.path, lower, upper, read_sql_query=self.fetch)

    def test_inclusive_fractional_bounds_and_duplicate_rows(self):
        self.assertCountEqual(self.read(1.5, 3),
                              [("low", 1.5, "b"), ("high", 3.0, "c"), ("high", 3.0, "c")])

    def test_equal_reversed_and_empty_bounds(self):
        self.assertEqual(len(self.read(3, 3)), 2)
        self.assertEqual(self.read(3, 1), [])
        self.assertEqual(self.read(5, 9), [])

    def test_invalid_values_are_rejected_before_query(self):
        for value in (None, True, float("nan"), float("inf"), "0 OR 1=1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.read(value, 4)

    def test_missing_file_and_read_only_connection(self):
        missing = self.path.with_name("missing.sql3")
        with self.assertRaises(sqlite3.OperationalError):
            read_score_range(missing, 0, 1, read_sql_query=self.fetch)
        self.assertFalse(missing.exists())
        before = self.path.read_bytes()
        def write(query, conn, *, params):
            conn.execute("UPDATE sampleSrc SET text = 'changed'")
        with self.assertRaises(sqlite3.OperationalError):
            read_score_range(self.path, 0, 3, read_sql_query=write)
        self.assertEqual(self.path.read_bytes(), before)

    def test_dataframe_columns_empty_shape_and_numpy_bounds(self):
        try:
            import numpy as np
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not installed")
        frame = read_score_range(self.path, np.int64(0), np.float64(3),
                                 read_sql_query=pd.read_sql_query)
        self.assertEqual(list(frame.columns), ["File", "InfoScoreSum", "text"])
        self.assertEqual(len(frame), 4)
        empty = read_score_range(self.path, 8, 9, read_sql_query=pd.read_sql_query)
        self.assertEqual(list(empty.columns), list(frame.columns))
        self.assertTrue(empty.empty)

    def test_active_score_button_uses_new_reader_and_keeps_sort(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "BertScript/Test_result_Vis.py").read_text(encoding="utf-8"))
        matches = [node for node in ast.walk(tree) if isinstance(node, ast.If)
                   and ast.unparse(node.test) == "button_id in ['btn_InfoScore']"]
        self.assertEqual(len(matches), 1)
        calls = [n for n in ast.walk(matches[0]) if isinstance(n, ast.Call)]
        readers = [n for n in calls if isinstance(n.func, ast.Name)
                   and n.func.id == "read_score_range"]
        self.assertEqual(len(readers), 1)
        self.assertEqual([ast.unparse(arg) for arg in readers[0].args],
                         ["DF_ALL_PreambleColsFN", "ISRange[0]", "ISRange[1]"])
        self.assertFalse(any(isinstance(n.func, ast.Name)
                             and n.func.id == "dfFromSQLite3" for n in calls))
        self.assertTrue(any(isinstance(n.func, ast.Attribute)
                            and n.func.attr == "sort_values" for n in calls))


if __name__ == "__main__":
    unittest.main()
