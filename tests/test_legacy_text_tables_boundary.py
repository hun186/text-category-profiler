"""Protect the three byte-exact historical legacy TXT tables.

No text-table interpretation, encoding assumptions, NLP/runtime imports,
or external I/O. In-repo lexical checks cannot rule out external callers.
"""
import hashlib
from pathlib import Path
import unittest

from scripts.bl001_research_caller_audit import ROOT, collect, load_catalog


OLD_DIR = ROOT / "text_category_profiler"
ARCHIVE_DIR = ROOT / "experiments/fixtures/legacy_text_tables"
ORIGINALS = {
    "EmojiAlll.txt": ("b603c8a3979c057b104ddb002aa50ff0588cdd9a", 36516),
    "特殊符號表.txt": ("f41651e616f86ca2c24f6bca9a1ed3242a7f1be7", 27063),
    "total.txt": ("21a5d2114b23f18c4d0a9b76f3a6cd9502f06133", 216074),
}


def blob_sha(data):
    return hashlib.sha1(("blob %d" % len(data)).encode("ascii") + b"\0" + data).hexdigest()


class LegacyTextTablesBoundaryTests(unittest.TestCase):
    def test_archived_blobs_preserve_original_git_identity(self):
        for name, (expected_sha, expected_bytes) in ORIGINALS.items():
            with self.subTest(name=name):
                self.assertFalse((OLD_DIR / name).exists())
                saved = (ARCHIVE_DIR / name).read_bytes()
                self.assertEqual(len(saved), expected_bytes)
                self.assertEqual(blob_sha(saved), expected_sha)

    def test_manifest_has_exact_relocated_paths(self):
        targets = load_catalog(ROOT)
        self.assertEqual(len(targets), 39)
        for name in ORIGINALS:
            with self.subTest(name=name):
                record = next(x for x in targets if x["basename"] == name)
                self.assertEqual(record["original_path"], "text_category_profiler/" + name)
                self.assertEqual(record["current_path"],
                                 "experiments/fixtures/legacy_text_tables/" + name)

    def test_no_direct_tracked_first_party_python_name_references(self):
        result = collect(ROOT)
        self.assertFalse(result["parse_errors"])
        self.assertEqual(
            [x for x in result["candidate_matches"] if x["basename"] in ORIGINALS],
            [],
            "Reevaluate direct first-party callers before moving archived source paths",
        )
        self.assertTrue(any("external" in item for item in result["limitations"]))

    def test_deployment_ftp_marker_is_untouched(self):
        marker = OLD_DIR / "FTPTEST/abc.txt"
        self.assertEqual(blob_sha(marker.read_bytes()),
                         "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f")

    def test_readme_states_external_and_provenance_limits(self):
        readme = (ARCHIVE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("external", readme)
        self.assertIn("provenance", readme)
        self.assertIn("original Git blob", readme)


if __name__ == "__main__":
    unittest.main()
