"""Original-blob and callsite safety for two punctuation comparison TXT files.

No text classification, data conversion, runtime imports or external services.
The repository scan is bounded to tracked first-party Python and is not an
assertion about dynamic or external/manual callers.
"""
import hashlib
from pathlib import Path
import unittest

from scripts.bl001_research_caller_audit import ROOT, collect, load_catalog


FIXTURE_DIR = ROOT / "experiments" / "fixtures" / "text_normalization"
ORIGINAL_DIR = ROOT / "text_category_profiler"
FILES = {
    "testFix.txt": ("e0bedf8bd7f5f940a187c807960ef76c9e5755df", 83),
    "testFix - 複製.txt": ("f890fe1ef548af6096588bc88464cc67fdf8b106", 59),
}


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


class PunctuationFixtureBoundaryTests(unittest.TestCase):
    def test_original_paths_gone_and_exact_git_blobs_preserved(self):
        for name, (sha, size) in FILES.items():
            with self.subTest(name=name):
                self.assertFalse((ORIGINAL_DIR / name).exists())
                data = (FIXTURE_DIR / name).read_bytes()
                self.assertEqual(len(data), size)
                self.assertEqual(git_blob_sha(data), sha)

    def test_punctuation_distinction_is_preserved(self):
        original = (FIXTURE_DIR / "testFix.txt").read_bytes()
        plain = (FIXTURE_DIR / "testFix - 複製.txt").read_bytes()
        self.assertNotEqual(original, plain)
        self.assertIn("，".encode("utf-8"), original)
        self.assertNotIn("，".encode("utf-8"), plain)

    def test_manifest_current_paths_are_exact_and_not_duplicate(self):
        targets = load_catalog(ROOT)
        for name in FILES:
            with self.subTest(name=name):
                item = next(entry for entry in targets if entry["basename"] == name)
                self.assertEqual(
                    item["original_path"], "text_category_profiler/" + name
                )
                self.assertEqual(
                    item["current_path"],
                    "experiments/fixtures/text_normalization/" + name,
                )

    def test_no_direct_tracked_first_party_python_mentions(self):
        result = collect(ROOT)
        matches = [
            hit for hit in result["candidate_matches"]
            if hit["basename"] in FILES
        ]
        self.assertEqual(result["parse_errors"], [])
        self.assertEqual(matches, [], "Recheck in-repo direct references before moving")
        self.assertIn("external", " ".join(result["limitations"]))

    def test_provenance_and_manual_caller_limits_documented(self):
        readme = (FIXTURE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("provenance", readme)
        self.assertIn("external", readme)
        self.assertIn("Git blob", readme)


if __name__ == "__main__":
    unittest.main()
