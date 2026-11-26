"""Disposable SQLite regressions for active visible-segment queries."""
import ast
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from BertScript.visualization_sample_reads import (
    read_visible_segments, read_max_partno,
)


class VisibleSegmentReadTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "片段 # 1.sql3"
        self.name = '中文 "引號" O\'Brien.txt'
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE sampleSrc (File TEXT, PartNO INTEGER, pred_Type TEXT, text TEXT)")
            conn.executemany("INSERT INTO sampleSrc VALUES (?, ?, ?, ?)", [
                (self.name, 3, "A", "three"),
                (self.name, 0, "A", "zero"),
                (self.name, 2, "B", "two"),
                (self.name, 1, "B", "one"),
                (self.name, 300, "C", "far"),
                ("other", 1, "C", "other"),
            ])

    def test_bound_name_and_legacy_range_order(self):
        self.assertEqual(read_visible_segments(self.path, self.name, 1, 3),
                         [(1, "B", "one"), (2, "B", "two")])
        self.assertEqual(read_visible_segments(self.path, self.name, 2, 2), [])
        self.assertEqual(read_visible_segments(self.path, self.name, 0, 1),
                         [(0, "A", "zero")])

    def test_fractional_bounds_keep_upper_minus_one_rule(self):
        self.assertEqual(read_visible_segments(self.path, self.name, 0.5, 2.5),
                         [(1, "B", "one")])

    def test_maximum_and_null_shape(self):
        self.assertEqual(read_max_partno(self.path, self.name), [300])
        self.assertEqual(read_max_partno(self.path, "missing"), [None])
        self.assertEqual(read_max_partno(self.path, '" OR 1=1 --'), [None])

    def test_missing_db_is_not_created_and_source_unchanged(self):
        before = self.path.read_bytes()
        read_visible_segments(self.path, self.name, 0, 300)
        read_max_partno(self.path, self.name)
        self.assertEqual(self.path.read_bytes(), before)
        missing = self.path.with_name("missing.sql3")
        self.assertEqual(read_visible_segments(missing, self.name, 0, 10), [])
        self.assertEqual(read_max_partno(missing, self.name), [])
        self.assertFalse(missing.exists())

    def test_active_entrypoints_use_read_boundary(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "BertScript/Test_result_Vis.py").read_text(encoding="utf-8"))
        for name, expected in [
            ("Build_VisDatatable", {"read_visible_segments", "read_max_partno"}),
            ("GetSrcList", {"read_sample_rows"}),
            ("Build_PerformanceTable", {"read_sample_rows"}),
        ]:
            node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
            calls = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name)}
            self.assertTrue(expected <= calls)
            self.assertNotIn("sqlite3Query", calls)
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "Build_VisDatatable")
        self.assertTrue(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                            and n.func.id == "min" and
                            any(isinstance(a, ast.Constant) and a.value == 300 for a in n.args)
                            for n in ast.walk(node)))


if __name__ == "__main__":
    unittest.main()
