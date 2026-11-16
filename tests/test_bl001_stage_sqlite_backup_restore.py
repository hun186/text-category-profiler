"""Private tempfile SQLite backup and restore acceptance (no WorkPool)."""
from contextlib import redirect_stdout
import io
import json
import unittest

from scripts.bl001_stage_sqlite_backup_restore import (
    check_private_backup_restore, main,
)


class PrivateBackupRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas required")

    def test_backup_and_restored_database_preserve_unknown_candidate(self):
        report = check_private_backup_restore(rows=15)
        self.assertEqual(report["status"], "PASS_PRIVATE_BACKUP_RESTORE")
        self.assertTrue(report["source_preserved"])
        self.assertTrue(report["backup_matches_source"])
        self.assertTrue(report["restored_matches_source"])
        self.assertTrue(report["unknown_candidate_preserved"])
        self.assertTrue(report["indexes_verified"])
        self.assertTrue(report["dependent_view_preserved"])
        self.assertEqual(report["candidate_owner_status"], "UNKNOWN")
        self.assertFalse(report["candidate_deletion_authorized"])
        self.assertFalse(report["production_workpool_verified"])

    def test_private_path_only_and_bounded_rows(self):
        for args in (["--rows", "0"], ["--rows", "4"], ["--rows", "501"]):
            with self.subTest(args=args), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["--db", "WorkPool/live.sqlite3"])
        self.assertEqual(caught.exception.code, 2)

    def test_cli_returns_structured_private_result(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["--rows", "8"])
        self.assertEqual(exit_code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "PASS_PRIVATE_BACKUP_RESTORE")
        self.assertFalse(payload["production_workpool_verified"])


if __name__ == "__main__":
    unittest.main()
