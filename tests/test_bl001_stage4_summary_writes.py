"""Summary write tests use disposable SQLite files, never production data."""
import ast
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from BertScript.visualization_summary_writes import write_summary_updates


class SummaryWriteTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "摘要 # 1.sql3"
        self.file = '中文 "引號" O\'Brien.txt'
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE sampleSrc (File TEXT, Summary TEXT, Other TEXT)")
            conn.executemany("INSERT INTO sampleSrc VALUES (?, ?, ?)", [
                (self.file, "old1", "A"), (self.file, "old2", "B"),
                ("second", "old3", "C"),
            ])

    def rows(self):
        with closing(sqlite3.connect(self.path)) as conn:
            return conn.execute("SELECT * FROM sampleSrc ORDER BY rowid").fetchall()

    def test_summary_and_filename_are_bound_and_other_columns_unchanged(self):
        summary = '中文 "引用" O\'Brien\n; UPDATE sampleSrc SET Summary="wrong"; --'
        self.assertEqual(write_summary_updates(self.path, [(summary, self.file)]), 2)
        self.assertEqual(self.rows(), [
            (self.file, summary, "A"), (self.file, summary, "B"),
            ("second", "old3", "C")])

    def test_unmatched_and_empty_are_no_ops(self):
        before = self.rows()
        self.assertEqual(write_summary_updates(self.path, []), 0)
        self.assertEqual(write_summary_updates(self.path, [("new", '" OR 1=1 --')]), 0)
        self.assertEqual(self.rows(), before)

    def test_missing_database_is_not_created(self):
        missing = self.path.with_name("missing.sql3")
        with self.assertRaises(sqlite3.OperationalError):
            write_summary_updates(missing, [("new", self.file)])
        self.assertFalse(missing.exists())

    def test_batch_rolls_back_when_later_update_fails(self):
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("""
                CREATE TRIGGER reject_second BEFORE UPDATE ON sampleSrc
                WHEN OLD.File = 'second'
                BEGIN SELECT RAISE(ABORT, 'fixture rejection'); END
            """)
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError):
            write_summary_updates(self.path, [("new1", self.file), ("new2", "second")])
        self.assertEqual(self.rows(), before)

    def test_duplicate_updates_preserve_last_input_order(self):
        write_summary_updates(self.path, [("first", self.file), ("last", self.file)])
        self.assertEqual([row[1] for row in self.rows()], ["last", "last", "old3"])

    def test_actual_application_calls_writer_after_collecting_summary_values(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "BertScript/Test_result_Vis.py").read_text(encoding="utf-8"))
        app = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "_run_visualization_application")
        summary = next(n for n in ast.walk(app) if isinstance(n, ast.If)
                       and isinstance(n.test, ast.Compare)
                       and isinstance(n.test.left, ast.Attribute)
                       and n.test.left.attr == "TextSummarization")
        calls = [n for n in ast.walk(summary) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)]
        writers = [n for n in calls if n.func.id == "write_summary_updates"]
        self.assertEqual(len(writers), 1)
        self.assertEqual([ast.unparse(arg) for arg in writers[0].args],
                         ["DF_All_sql3File", "summary_updates"])
        self.assertNotIn("sqlite3Query", {n.func.id for n in calls})
        self.assertFalse(any(isinstance(n, ast.JoinedStr) and
                             "UPDATE sampleSrc" in ast.unparse(n)
                             for n in ast.walk(summary)))


if __name__ == "__main__":
    unittest.main()
