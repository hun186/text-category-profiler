"""Characterization of the bounded BL-001 static caller audit (stdlib only)."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.bl001_research_caller_audit import (
    ROOT, collect, load_catalog, scan_source,
)


class ResearchCallerAuditTests(unittest.TestCase):
    def test_catalog_tracks_original_and_relocated_paths(self):
        targets = load_catalog(ROOT)
        self.assertEqual(len(targets), 39)
        self.assertEqual(
            next(x for x in targets if x["basename"] == "RAGTest.json")["current_path"],
            "experiments/fixtures/research_samples/RAGTest.json",
        )
        self.assertEqual(
            sum(x["original_path"] != x["current_path"] for x in targets), 2
        )

    def test_ast_literals_and_comments_are_not_conflated(self):
        targets = [{"original_path": "data/example.txt",
                    "current_path": "data/example.txt",
                    "basename": "example.txt"}]
        source = 'file = "example.txt"\n# "example.txt" old note\n'
        rows, error = scan_source("demo.py", source, targets)
        self.assertIsNone(error)
        self.assertEqual([x["evidence"] for x in rows],
                         ["ast_string_literal", "text_or_comment"])
        self.assertEqual(rows[0]["matching_full_paths"], [])

    def test_ambiguous_basename_does_not_claim_unique_caller(self):
        targets = [
            {"original_path": "a/report.xlsx", "current_path": "a/report.xlsx",
             "basename": "report.xlsx"},
            {"original_path": "b/report.xlsx", "current_path": "b/report.xlsx",
             "basename": "report.xlsx"},
        ]
        rows, error = scan_source("demo.py", 'fn = "report.xlsx"\n', targets)
        self.assertIsNone(error)
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["basename_ambiguous"])
        self.assertEqual(rows[0]["candidate_original_paths"],
                         ["a/report.xlsx", "b/report.xlsx"])

    def test_parse_failures_are_reported_not_silently_omitted(self):
        targets = [{"original_path": "data/example.txt",
                    "current_path": "data/example.txt",
                    "basename": "example.txt"}]
        rows, error = scan_source("broken.py", 'x = "example.txt"\nif :\n', targets)
        self.assertEqual(error, "SyntaxError")
        self.assertEqual(rows[0]["evidence"], "text_or_comment")

    def test_real_manual_similarity_file_literals_remain_visible(self):
        result = collect(ROOT, ["text_category_profiler/text/similarity_utils.py"])
        hits = result["candidate_matches"]
        source_hits = [x for x in hits if x["evidence"] == "ast_string_literal"
                       and "陈德铭呼吁美方为中国赴美企业提供公平公正商业环境" in x["basename"]]
        self.assertGreaterEqual(len(source_hits), 2)
        self.assertEqual(result["parse_errors"], [])

    def test_synthetic_checkout_needs_no_runtime_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "experiments/fixtures").mkdir(parents=True)
            (root / "experiments/fixtures/bl001_residual_inventory.json").write_text(
                json.dumps({"entries": [{
                    "path": "text_category_profiler/example.txt",
                    "sha": "not-used-here", "size_bytes": 0,
                }] * 12}), encoding="utf-8",
            )
            (root / "experiments/fixtures/bl001_similarity_experiment_inventory.json").write_text(
                json.dumps({"entries": [
                    {"path": f"test/{i:02d}.txt"} for i in range(27)
                ]}), encoding="utf-8",
            )
            # load_catalog deliberately rejects duplicate original paths.
            with self.assertRaises(AssertionError):
                load_catalog(root)


if __name__ == "__main__":
    unittest.main()
