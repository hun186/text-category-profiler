"""SQLite WAL backed-up committed rows / unknown candidate: PRIVATE ONLY."""
from contextlib import redirect_stdout
import io
import json
import unittest

from scripts.bl001_stage_sqlite_wal_backup import main, private_wal_backup


class PrivateWalBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas required")

    def test_committed_wal_changes_are_in_detached_backup_and_restore(self):
        result = private_wal_backup(rows=12)
        self.assertEqual(result["status"], "PASS_PRIVATE_WAL_BACKUP")
        self.assertTrue(result["source_wal_detected_and_refused_for_offline_inventory"])
        self.assertTrue(result["committed_wal_rows_in_backup"])
        self.assertTrue(result["uncommitted_wal_rows_excluded"])
        self.assertTrue(result["backup_restored_with_indexes_and_view"])
        self.assertTrue(result["unknown_candidate_preserved"])
        self.assertTrue(result["unrelated_foreign_key_integrity_preserved"])
        self.assertEqual(result["candidate_owner_status"], "UNKNOWN")
        self.assertFalse(result["candidate_deletion_authorized"])
        self.assertFalse(result["production_workpool_verified"])

    def test_backup_verifier_rejects_foreign_key_violation(self):
        import tempfile
        import sqlite3
        from pathlib import Path
        from contextlib import closing
        from scripts.bl001_stage_sqlite_wal_backup import _verify_detached
        with tempfile.TemporaryDirectory(prefix="ki012-broken-fk-private-") as tmp:
            path = Path(tmp) / "broken-fk.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE "lookup_parent" '
                           '("id" INTEGER PRIMARY KEY, "name" TEXT)')
                db.execute('CREATE TABLE "lookup_child" '
                           '("parent_id" INTEGER REFERENCES "lookup_parent"("id"))')
                db.execute('INSERT INTO "lookup_child" VALUES (999)')
                db.commit()
            with self.assertRaisesRegex(AssertionError, "foreign-key"):
                _verify_detached(path, 10)

    def test_bounds_and_no_external_db_path(self):
        for args in (["--rows", "9"], ["--rows", "501"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as err:
            main(["--db", "WorkPool/live.sqlite3"])
        self.assertEqual(err.exception.code, 2)

    def test_cli_structured_result(self):
        out = io.StringIO()
        with redirect_stdout(out):
            status = main(["--rows", "10"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PASS_PRIVATE_WAL_BACKUP")


if __name__ == "__main__":
    unittest.main()
