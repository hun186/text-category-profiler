"""Git blob identity in both legacy-root audit and package census.

No legacy modules are imported, no external services, no file rewrites.
"""
import ast
from pathlib import Path
import unittest
from unittest import mock

from scripts.bl001_git_blob_identity import (
    git_blob_sha, legacy_git_blob_bytes,
)
from scripts import bl001_legacy_root_audit as legacy
from scripts import bl001_package_census as census


class SharedLegacyBlobIdentityTests(unittest.TestCase):
    def test_all_audits_use_same_function_objects_not_copied_algorithms(self):
        self.assertIs(legacy.blob_sha, git_blob_sha)
        self.assertIs(legacy.legacy_git_blob_bytes, legacy_git_blob_bytes)
        self.assertIs(census.git_blob_sha, git_blob_sha)
        self.assertIs(census.legacy_git_blob_bytes, legacy_git_blob_bytes)

    def test_only_exact_git_blob_digest_and_length_authorize_crlf(self):
        blob = b"legacy first\nlegacy second\n"
        sha = git_blob_sha(blob)
        windows = blob.replace(b"\n", b"\r\n")
        self.assertEqual(legacy_git_blob_bytes(windows, sha, len(blob)), blob)
        self.assertEqual(legacy_git_blob_bytes(blob, sha, len(blob)), blob)
        self.assertEqual(
            legacy_git_blob_bytes(windows, sha, len(blob) + 1), windows,
        )
        mutated = b"legacy first\r\nchanged\r\n"
        self.assertEqual(
            legacy_git_blob_bytes(mutated, sha, len(blob)), mutated,
        )
        bare_cr = b"legacy first\rlegacy second\r"
        self.assertEqual(
            legacy_git_blob_bytes(bare_cr, sha, len(blob)), bare_cr,
        )

    def test_legacy_audit_reports_unknown_content_instead_of_normalizing_it(self):
        item = legacy.load_catalog(legacy.ROOT)[0]
        target = legacy.ROOT / item["path"]
        source_read = Path.read_bytes
        def fake_read(path):
            result = source_read(path)
            if path == target:
                return b"modified legacy bytes"
            return result
        with mock.patch.object(Path, "read_bytes", fake_read):
            report = legacy.audit(legacy.ROOT, [])
        row = next(r for r in report["preservation"]
                   if r["path"] == item["path"])
        self.assertFalse(
            row["blob_matches_baseline"] and row["size_matches_baseline"]
        )
        self.assertFalse(any(x.get("external_callers_verified")
                             for x in [report]))

    def test_portable_audits_agree_all_preserved_git_objects_in_checkout(self):
        base = legacy.audit(legacy.ROOT, [])
        census_report = census.audit_package(census.ROOT)
        self.assertEqual(len(base["preservation"]), 13)
        self.assertEqual(census_report["identity_failures"], [])
        self.assertTrue(all(
            x["blob_matches_baseline"] and x["size_matches_baseline"]
            and x["canonical_exists"]
            for x in base["preservation"]
        ))

    def test_helper_is_dependency_light_and_writes_nothing(self):
        source = (Path(__file__).resolve().parents[1]
                  / "scripts/bl001_git_blob_identity.py")
        syntax = ast.parse(source.read_text(encoding="utf-8"))
        self.assertEqual(
            {alias.name for n in syntax.body if isinstance(n, ast.Import)
             for alias in n.names}, {"hashlib"},
        )
        self.assertFalse(any(isinstance(n, ast.ImportFrom)
                             for n in ast.walk(syntax)))


if __name__ == "__main__":
    unittest.main()
