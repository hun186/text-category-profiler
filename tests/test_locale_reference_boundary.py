"""Dependency-light boundary for one historical PDF reference relocation.

PDF bytes are not parsed or rewritten. No model, network, or dataset access.
"""
from pathlib import Path
import hashlib
import unittest


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "text_category_profiler" / "Table of locales - MoodleDocs.pdf"
NEW = ROOT / "docs" / "references" / "table-of-locales-moodledocs.pdf"
README = ROOT / "docs" / "references" / "README.md"
ORIGINAL_BLOB = "189909957805328d356495130b2899529504cb78"
ORIGINAL_SIZE = 353177


def git_blob_sha(data):
    prefix = ("blob %d" % len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(prefix + data).hexdigest()


class LocaleReferenceBoundaryTests(unittest.TestCase):
    def test_original_pdf_bytes_preserved_without_parsing(self):
        data = NEW.read_bytes()
        self.assertEqual(len(data), ORIGINAL_SIZE)
        self.assertTrue(data.startswith(b"%PDF-"))
        self.assertEqual(git_blob_sha(data), ORIGINAL_BLOB)

    def test_historical_package_root_location_removed(self):
        self.assertFalse(OLD.exists())
        self.assertTrue(NEW.is_file())
        self.assertFalse(str(NEW.relative_to(ROOT)).startswith("text_category_profiler/"))

    def test_python_sources_do_not_reference_historical_pdf_name(self):
        needle = OLD.name
        offenders = []
        # Scan checked-out .py sources (including legacy snapshots) without imports.
        for path in ROOT.rglob("*.py"):
            if path == Path(__file__).resolve() or "__pycache__" in path.parts:
                continue
            if needle in path.read_text(encoding="utf-8", errors="replace"):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [], "Update callers before moving the PDF")

    def test_documentation_records_identity_and_external_caller_limit(self):
        doc = README.read_text(encoding="utf-8")
        self.assertIn(OLD.relative_to(ROOT).as_posix(), doc)
        self.assertIn(NEW.relative_to(ROOT).as_posix(), doc)
        self.assertIn(ORIGINAL_BLOB, doc)
        self.assertIn("External/manual consumers", doc)
        self.assertIn("not verified", doc)


if __name__ == "__main__":
    unittest.main()
