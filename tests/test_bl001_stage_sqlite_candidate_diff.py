"""Read-only offline SQLite candidate diff; source bytes unchanged."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_candidate_diff import compare_offline_copies, main


class OfflineCandidateSnapshotDiffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ki012-private-candidate-diff-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.before = root / "before.sqlite3"
        self.after = root / "after.sqlite3"
        for path in (self.before, self.after):
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE sampleSrc ("index" INTEGER, "text" TEXT)')
                db.execute('CREATE INDEX "text_Index" ON sampleSrc("text")')
                db.commit()

    @staticmethod
    def candidate(path, suffix):
        name = "__bl001_stage_" + suffix
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE "' + name + '" ("text" TEXT)')
            db.commit()

    def test_stopped_copies_with_no_candidates_are_clear_but_not_production(self):
        a, b = self.before.read_bytes(), self.after.read_bytes()
        result = compare_offline_copies(self.before, self.after)
        self.assertEqual(result["status"], "PASS_NO_CANDIDATES")
        self.assertEqual(result["owner_status"], "UNKNOWN")
        self.assertFalse(result["deletion_authorized"])
        self.assertFalse(result["production_workpool_verified"])
        self.assertEqual(self.before.read_bytes(), a)
        self.assertEqual(self.after.read_bytes(), b)

    def test_added_removed_unchanged_and_truncated_metadata_are_exact(self):
        for i in range(25):
            self.candidate(self.before, f"{i:032x}")
        self.candidate(self.before, "f" * 32)
        for i in range(25, 50):
            self.candidate(self.after, f"{i:032x}")
        self.candidate(self.after, "f" * 32)
        a, b = self.before.read_bytes(), self.after.read_bytes()
        out = compare_offline_copies(self.before, self.after)
        self.assertEqual(out["status"], "REVIEW_REQUIRED")
        self.assertEqual(out["unchanged_candidate_count"], 1)
        self.assertEqual(out["added_candidate_count"], 25)
        self.assertEqual(out["removed_candidate_count"], 25)
        self.assertTrue(out["added_names_truncated"])
        self.assertTrue(out["removed_names_truncated"])
        self.assertEqual(len(out["added_candidate_names"]), 20)
        self.assertEqual(len(out["removed_candidate_names"]), 20)
        self.assertFalse(out["deletion_authorized"])
        self.assertEqual(self.before.read_bytes(), a)
        self.assertEqual(self.after.read_bytes(), b)

    def test_equal_count_but_different_schema_names_fail_closed(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_candidate_diff as mod
        self.candidate(self.before, "a" * 32)
        self.candidate(self.after, "b" * 32)
        original = mod._read_candidate_names
        def replaced_scan(path):
            candidates, malformed = original(path)
            if path == self.after:
                # Simulate a changed schema between inventory and scan;
                # names are different but count stays the same.
                return {"__bl001_stage_" + "c" * 32}, malformed
            return candidates, malformed
        before_bytes = self.before.read_bytes()
        after_bytes = self.after.read_bytes()
        with patch.object(mod, "_read_candidate_names",
                          side_effect=replaced_scan):
            result = compare_offline_copies(self.before, self.after)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("snapshot_changed_or_inconsistent", result["issues"])
        self.assertNotIn("removed_candidate_count", result)
        self.assertFalse(result["deletion_authorized"])
        self.assertEqual(self.before.read_bytes(), before_bytes)
        self.assertEqual(self.after.read_bytes(), after_bytes)

    def test_case_variant_prefix_in_diff_requires_review(self):
        with closing(sqlite3.connect(self.after)) as db:
            db.execute('CREATE TABLE "__BL001_STAGE_'
                       + "a" * 32 + '" ("text" TEXT)')
            db.commit()
        report = compare_offline_copies(self.before, self.after)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["added_candidate_count"], 0)
        self.assertEqual(report["added_malformed_prefix_count"], 1)
        self.assertFalse(report["deletion_authorized"])

    def test_malformed_prefix_counts_and_no_cleanup_inferences(self):
        with closing(sqlite3.connect(self.before)) as db:
            db.execute('CREATE TABLE "__bl001_stage_unknown_old" (v TEXT)')
            db.commit()
        with closing(sqlite3.connect(self.after)) as db:
            db.execute('CREATE TABLE "__bl001_stage_unknown_new" (v TEXT)')
            db.commit()
        result = compare_offline_copies(self.before, self.after)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["added_malformed_prefix_count"], 1)
        self.assertEqual(result["removed_malformed_prefix_count"], 1)
        self.assertFalse(result["deletion_authorized"])

    def test_identity_workpool_sidecars_and_missing_fail_closed(self):
        self.assertEqual(compare_offline_copies(self.before, self.before)["status"],
                         "UNVERIFIABLE")
        original = self.before.read_bytes()
        pool = Path(self.tmp.name) / "WorkPool-backup"
        pool.mkdir()
        live = pool / "live.sqlite3"
        import shutil
        shutil.copyfile(self.after, live)
        deny = compare_offline_copies(self.before, live)
        self.assertEqual(deny["status"], "UNVERIFIABLE")
        self.assertIn("after:workpool_path_not_allowed", deny["issues"])
        self.assertEqual(self.before.read_bytes(), original)
        Path(str(self.after) + "-wal").write_bytes(b"fake")
        self.assertEqual(
            compare_offline_copies(self.before, self.after)["status"],
            "UNVERIFIABLE",
        )
        self.assertEqual(
            compare_offline_copies(self.before, self.after.parent / "missing")[
                "status"], "UNVERIFIABLE",
        )

    def test_copy_modified_during_metadata_scan_is_unverifiable(self):
        from unittest.mock import patch
        import os
        from scripts import bl001_stage_sqlite_candidate_diff as mod

        original = mod._read_candidate_names
        def changed_after_scan(path):
            result = original(path)
            if path == self.after:
                # Private file only: force a metadata change while preserving
                # the candidate name sets. This must fail closed.
                stat = path.stat()
                os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000))
            return result

        with patch.object(mod, "_read_candidate_names",
                          side_effect=changed_after_scan):
            report = compare_offline_copies(self.before, self.after)
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("offline_copy_changed_during_diff", report["issues"])
        self.assertFalse(report["deletion_authorized"])
        self.assertNotIn("added_candidate_count", report)

    def test_sidecar_created_during_second_scan_refuses_diff(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_candidate_diff as mod
        original = mod._read_candidate_names
        sidecar = Path(str(self.after) + "-wal")
        before_bytes, after_bytes = self.before.read_bytes(), self.after.read_bytes()
        def add_sidecar_after_scan(path):
            names = original(path)
            if path == self.after:
                sidecar.write_bytes(b"pending-after-inventory")
            return names
        with patch.object(mod, "_read_candidate_names",
                          side_effect=add_sidecar_after_scan):
            result = compare_offline_copies(self.before, self.after)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("offline_copy_changed_during_diff", result["issues"])
        self.assertNotIn("added_candidate_count", result)
        self.assertFalse(result["deletion_authorized"])
        self.assertEqual(self.before.read_bytes(), before_bytes)
        self.assertEqual(self.after.read_bytes(), after_bytes)
        self.assertEqual(sidecar.read_bytes(), b"pending-after-inventory")

    def test_hardlink_created_during_second_scan_refuses_diff(self):
        import os
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_candidate_diff as mod
        link = Path(self.tmp.name) / "late-hardlink.sqlite3"
        original = mod._read_candidate_names
        def link_after_scan(path):
            result = original(path)
            if path == self.after:
                try:
                    os.link(path, link)
                except (OSError, NotImplementedError):
                    self.skipTest("Hard links unsupported on this filesystem")
            return result
        with patch.object(mod, "_read_candidate_names",
                          side_effect=link_after_scan):
            report = compare_offline_copies(self.before, self.after)
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("offline_copy_changed_during_diff", report["issues"])
        self.assertFalse(report["deletion_authorized"])

    def test_invalid_path_fails_as_structured_unverifiable(self):
        invalid = "private\\x00copy/db.sqlite3".replace("\\x00", "\x00")
        report = compare_offline_copies(invalid, self.after)
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("copy_identity_not_verifiable", report["issues"])
        self.assertFalse(report["deletion_authorized"])

    def test_cli_exit_codes(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--before", str(self.before),
                                   "--after", str(self.after)]), 0)
        self.candidate(self.after, "a" * 32)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--before", str(self.before),
                                   "--after", str(self.after)]), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as err:
            main(["--db", str(self.before)])
        self.assertEqual(err.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
