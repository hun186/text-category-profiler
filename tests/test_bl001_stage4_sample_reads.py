"""Temporary SQLite fixtures for the Stage 4 read-only sample boundary."""
import ast
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from BertScript.visualization_sample_reads import read_sample_rows


class Stage4SampleReadsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "樣本 # 1.sql3"
        self.name = '中文 "引號" O\'Brien.txt'
        with sqlite3.connect(self.path) as connection:
            connection.execute("CREATE TABLE sampleSrc (File, Src, PartNO, pred_Type, text)")
            connection.executemany("INSERT INTO sampleSrc VALUES (?, ?, ?, ?, ?)", [
                (self.name, "src2", 2, "B", "第二"),
                (self.name, "src1", 1, "A", "第一"),
                ("File", "wrong", 1, "C", "other"),
                ("other", "other", 0, "D", "other"),
            ])

    def test_literal_name_and_single_column_legacy_shape(self):
        self.assertEqual(read_sample_rows(self.path,
            "SELECT Src FROM sampleSrc WHERE File = ? ORDER BY PartNO", (self.name,)),
            ["src1", "src2"])

    def test_segments_keep_order_and_tuple_shape(self):
        self.assertEqual(read_sample_rows(self.path,
            "SELECT PartNO,pred_Type,text FROM sampleSrc WHERE File = ? ORDER BY PartNO",
            (self.name,)), [(1, "A", "第一"), (2, "B", "第二")])

    def test_sql_like_text_is_only_a_parameter(self):
        query = "SELECT Src FROM sampleSrc WHERE File = ?"
        self.assertEqual(read_sample_rows(self.path, query, ('" OR 1=1 --',)), [])
        self.assertEqual(read_sample_rows(self.path, query, ("File",)), ["wrong"])

    def test_missing_file_is_not_created(self):
        missing = self.path.with_name("missing.sql3")
        self.assertEqual(read_sample_rows(missing, "SELECT Src FROM sampleSrc", ()), [])
        self.assertFalse(missing.exists())

    def test_write_rejected_and_database_unchanged(self):
        with self.assertRaises(sqlite3.OperationalError):
            read_sample_rows(self.path, "DELETE FROM sampleSrc WHERE File = ?", (self.name,))
        self.assertEqual(read_sample_rows(self.path, "SELECT COUNT(*) FROM sampleSrc", ()), [4])

    def test_active_builder_binds_both_file_queries(self):
        source = (Path(__file__).resolve().parents[1] /
                  "BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        builder = next(n for n in tree.body if isinstance(n, ast.ClassDef)
                       and n.name == "VisDatatableRowsListBuilder")
        run = next(n for n in builder.body if isinstance(n, ast.FunctionDef) and n.name == "run")
        calls = [n for n in ast.walk(run) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name) and n.func.id == "read_sample_rows"]
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(ast.unparse(call.args[2]), "(file,)")
        query_strings = [n.value for n in ast.walk(run) if isinstance(n, ast.Constant)
                         and isinstance(n.value, str) and "WHERE File = ?" in n.value]
        self.assertEqual(len(query_strings), 2)


if __name__ == "__main__":
    unittest.main()
