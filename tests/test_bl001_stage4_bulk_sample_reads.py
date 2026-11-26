"""Set-based read-only Stage 4 sample queries on temporary SQLite fixtures."""
import ast
from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from BertScript.visualization_sample_reads import (
    read_labels_for_files, read_predictions_for_files,
)


class Stage4BulkSampleReadsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "樣本 # 2.sql3"
        self.name = '中文 "引號" O\'Brien.txt'
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("CREATE TABLE sampleSrc (File TEXT COLLATE NOCASE, pred_Type TEXT)")
            conn.executemany("INSERT INTO sampleSrc VALUES (?, ?)", [
                (self.name, "A"), (self.name, "A"), (self.name, "B"),
                ("Case.txt", "B"), ("Case.txt", None), ("other", "C"),
                ("File", "D"), ("None", "N"),
            ])
            conn.commit()

    def test_duplicate_input_does_not_remove_real_prediction_duplicates(self):
        names = [self.name, self.name, "CASE.TXT", "case.txt"]
        self.assertEqual(Counter(read_predictions_for_files(self.path, names)),
                         Counter([(self.name, "A"), (self.name, "A"),
                                  (self.name, "B"), ("Case.txt", "B"),
                                  ("Case.txt", None)]))
        self.assertEqual(set(read_labels_for_files(self.path, names)), {"A", "B", None})

    def test_large_generator_and_sql_like_values_are_literal(self):
        names = (name for name in [f"missing-{i}" for i in range(2500)]
                 + [self.name, '" OR 1=1 --', "File"])
        self.assertEqual(set(read_labels_for_files(self.path, names)), {"A", "B", "D"})

    def test_nonstring_conversion_preserves_legacy_string_values(self):
        self.assertEqual(read_labels_for_files(self.path, [None]), ["N"])

    def test_empty_missing_and_source_unchanged(self):
        original = self.path.read_bytes()
        self.assertEqual(read_predictions_for_files(self.path, []), [])
        self.assertEqual(read_labels_for_files(self.path, []), [])
        read_predictions_for_files(self.path, [self.name])
        read_labels_for_files(self.path, [self.name])
        self.assertEqual(self.path.read_bytes(), original)
        missing = self.path.with_name("missing.sql3")
        self.assertEqual(read_predictions_for_files(missing, [self.name]), [])
        self.assertFalse(missing.exists())

    def test_active_chart_and_both_label_paths_use_bound_helpers(self):
        source = (Path(__file__).resolve().parents[1] /
                  "BertScript/Test_result_Vis.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        preds = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                     and node.name == "BuildPredsdf")
        def calls(node, name):
            return [n for n in ast.walk(node) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name) and n.func.id == name]
        self.assertEqual(len(calls(preds, "read_predictions_for_files")), 1)
        self.assertEqual(len(calls(preds, "read_sample_rows")), 1)
        self.assertEqual(len(calls(tree, "read_labels_for_files")), 2)


if __name__ == "__main__":
    unittest.main()
