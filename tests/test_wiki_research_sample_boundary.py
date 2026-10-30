"""Byte-exact boundary for a historical, unverified Wikipedia-derived text sample.

Pure stdlib/file checks only. No model, dataset pipeline or network calls.
"""
import hashlib
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "text_category_profiler" / "sample_data" / "俄烏戰爭@wiki"
NEW = ROOT / "experiments" / "fixtures" / "wiki_article" / "俄烏戰爭@wiki"
README = NEW.parent / "README.md"
BLOB_SHA = "85e7f0573296fe49f603a6bec14c043b378e64db"
ORIGINAL_SIZE = 83123


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


class WikiResearchSampleBoundaryTests(unittest.TestCase):
    def test_unchanged_original_git_blob_and_length(self):
        data = NEW.read_bytes()
        self.assertEqual(len(data), ORIGINAL_SIZE)
        self.assertEqual(git_blob_sha(data), BLOB_SHA)

    def test_legacy_package_data_location_is_absent(self):
        self.assertFalse(OLD.exists())
        self.assertTrue(NEW.is_file())
        self.assertNotIn("text_category_profiler", NEW.relative_to(ROOT).parts)

    def test_no_tracked_python_source_uses_historical_filename(self):
        # An explicit literal check, not an exhaustive dynamic/external caller audit.
        proc = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"],
            cwd=ROOT, capture_output=True, check=True,
        )
        offenders = []
        for raw in proc.stdout.split(b"\0"):
            if not raw:
                continue
            name = raw.decode("utf-8", errors="surrogateescape")
            path = ROOT / name
            if path == Path(__file__).resolve() or not path.is_file():
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if OLD.name in source:
                offenders.append(name)
        self.assertEqual(offenders, [], "Review callers before changing source paths")

    def test_readme_discloses_provenance_and_compatibility_limits(self):
        readme = README.read_text(encoding="utf-8")
        for value in (
            OLD.relative_to(ROOT).as_posix(),
            NEW.relative_to(ROOT).as_posix(),
            BLOB_SHA,
            str(ORIGINAL_SIZE),
            "not verified",
            "External/manual callers",
            "licensing",
        ):
            self.assertIn(value, readme)


if __name__ == "__main__":
    unittest.main()
