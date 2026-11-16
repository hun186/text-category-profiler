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
