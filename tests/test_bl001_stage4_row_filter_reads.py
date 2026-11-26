"""SQLite and active-wrapper regression coverage for Stage 4 row filtering."""
import ast
from collections import Counter
from contextlib import closing
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from BertScript.visualization_row_filter_reads import (
    read_files_for_labels, read_matching_block_counts,
)


class RowFilterReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "樣本 # 3.sql3"
        self.file = '中文 "引號".txt'
        self.label = "O'Brien"
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("CREATE TABLE sampleSrc (File TEXT, pred_Type TEXT, text TEXT)")
            conn.executemany("INSERT INTO sampleSrc VALUES (?, ?, ?)", [
                (self.file, self.label, "alpha"),
                (self.file, self.label, "beta"),
                (self.file, self.label, "alpha beta"),
                (self.file, self.label, "alpha beta"),
                (self.file, self.label, "0"),
                (self.file, self.label, None),
                (self.file, "other", "alpha"),
                ("second", self.label, "unrelated"),
                ("third", "other", "beta"),
            ])

    def test_original_sql_bitwise_or_failure_is_reproduced(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.create_function("REGEXP", 2, lambda pattern, text:
                                 bool(re.search(str(pattern), text or "")))
            rows = conn.execute(
                'SELECT text FROM sampleSrc WHERE text REGEXP ("alpha" | "beta")'
            ).fetchall()
        self.assertEqual(rows, [("0",)])

    def test_multiple_regex_or_counts_source_row_once(self):
        totals, matched = read_matching_block_counts(
            self.path, [self.file, "second", self.file], [self.label, self.label],
            ["alpha", "beta", "alpha"])
        self.assertEqual(dict(totals), {self.file: 6, "second": 1})
        self.assertEqual(matched, [(self.file, 4)])

    def test_single_regex_flags_groups_and_backreferences(self):
        _, matched = read_matching_block_counts(
            self.path, [self.file], [self.label], [r"(?i)^ALPHA$"])
        self.assertEqual(matched, [(self.file, 1)])
        _, matched = read_matching_block_counts(
            self.path, [self.file], [self.label], [r"(?P<x>alpha)", r"(?P<x>beta)"])
        self.assertEqual(matched, [(self.file, 4)])
        _, matched = read_matching_block_counts(
            self.path, [self.file], [self.label], [r"(alpha)\s+beta", r"^beta$"])
        self.assertEqual(matched, [(self.file, 3)])

    def test_no_keyword_no_label_and_missing_database(self):
        self.assertEqual(read_matching_block_counts(
            self.path, [self.file], [self.label], []), ([(self.file, 6)], []))
        self.assertEqual(read_matching_block_counts(
            self.path, [self.file], [], ["alpha"]), ([], []))
        missing = self.path.with_name("missing.sql3")
        self.assertEqual(read_files_for_labels(missing, [self.label]), [])
        self.assertEqual(read_matching_block_counts(missing, [self.file],
                         [self.label], ["alpha"]), ([], []))
        self.assertFalse(missing.exists())

    def test_bound_values_large_inputs_and_no_source_mutation(self):
        original = self.path.read_bytes()
        labels = [f"missing-{i}" for i in range(2500)] + [self.label]
        self.assertEqual(set(read_files_for_labels(self.path, labels)),
                         {self.file, "second"})
        names = [f"missing-{i}" for i in range(2500)] + [self.file, '" OR 1=1 --']
        totals, matched = read_matching_block_counts(
            self.path, names, labels, [r"alpha|beta"])
        self.assertEqual(totals, [(self.file, 6)])
        self.assertEqual(matched, [(self.file, 4)])
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_pattern_is_explicit(self):
        with self.assertRaises(re.error):
            read_matching_block_counts(self.path, [self.file], [self.label], ["["])

    def test_actual_wrapper_wiring_and_empty_label_passthrough(self):
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "BertScript/Test_result_Vis.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "RowsFilter")
        calls = {n.func.id for n in ast.walk(node) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Name)}
        self.assertIn("read_files_for_labels", calls)
        self.assertIn("read_matching_block_counts", calls)
        self.assertNotIn("sqlite3Query", calls)
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<wrapper>", "exec"),
             namespace)
        sentinel = object()
        self.assertIs(namespace["RowsFilter"](sentinel, [], self.path, ["alpha"]), sentinel)

    def test_dataframe_join_preserves_filter_and_empty_keyword_column(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not installed")
        tree = ast.parse((Path(__file__).resolve().parents[1] /
                          "BertScript/Test_result_Vis.py").read_text(encoding="utf-8"))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == "RowsFilter")
        namespace = dict(pd=pd, read_files_for_labels=read_files_for_labels,
                         read_matching_block_counts=read_matching_block_counts)
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<wrapper>", "exec"),
             namespace)
        frame = pd.DataFrame({"File": [self.file, "second", "third"],
                              "NumberOfMatchingBlock": [0, 0, 0],
                              "NumberOfMatchingBlockWithKW": ["", "", ""],
                              "untouched": [11, 22, 33]})
        run = namespace["RowsFilter"]
        actual = run(frame, [self.label], self.path, ["alpha", "beta"])
        self.assertEqual(actual.to_dict("records"), [{
            "File": self.file, "untouched": 11, "NumberOfMatchingBlock": 6,
            "NumberOfMatchingBlockWithKW": 4}])
        no_kw = run(frame, [self.label], self.path, [])
        self.assertEqual(set(no_kw["File"]), {self.file, "second"})
        self.assertEqual(list(no_kw["NumberOfMatchingBlockWithKW"]), ["", ""])
        self.assertEqual(list(frame["NumberOfMatchingBlock"]), [0, 0, 0])


if __name__ == "__main__":
    unittest.main()
