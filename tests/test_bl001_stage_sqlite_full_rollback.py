"""Real SQLite quota failure contract, in a disposable private database."""
from contextlib import redirect_stdout
import io
import json
import unittest

from scripts.bl001_stage_sqlite_full_rollback import (
    main, run_private_sqlite_full,
)


class PrivateSqliteFullRollbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas needed")

    def test_real_sqlite_full_preserves_original_and_indexes(self):
        report = run_private_sqlite_full(rows=120, repeat=64)
        self.assertEqual(report["status"], "PASS_SQLITE_FULL_ROLLBACK")
        self.assertIn(report["sqlite_error_name"], ("SQLITE_FULL",))
        self.assertTrue(report["original_rows_preserved"])
        self.assertTrue(report["text_index_preserved"])
        self.assertTrue(report["dependent_view_preserved"])
        self.assertTrue(report["unrelated_table_preserved"])
        self.assertEqual(report["integrity_check"], "ok")
        self.assertEqual(report["candidate_tables_remaining"], 0)
        self.assertFalse(report["production_workpool_verified"])
        self.assertTrue(report["post_quota_retry_passed"])
        self.assertEqual(report["post_quota_retry_rows"], 120)
        self.assertEqual(report["post_quota_retry_integrity"], "ok")
        self.assertEqual(report["quota_at_swap"]["page_count"],
                         report["quota_at_swap"]["max_page_count"])

    def test_second_quota_failure_then_retry_is_consistent(self):
        # A second invocation gets a fresh private DB; never reuses external DB.
        report = run_private_sqlite_full(rows=140, repeat=96)
        self.assertEqual(report["status"], "PASS_SQLITE_FULL_ROLLBACK")
        self.assertEqual(report["post_quota_retry_rows"], 140)
        self.assertTrue(report["original_rows_preserved"])
        self.assertTrue(report["post_quota_retry_passed"])
        self.assertFalse(report["production_workpool_verified"])

    def test_args_bounded_and_no_external_db(self):
        for args in (["--rows", "99"], ["--rows", "2001"],
                     ["--repeat", "63"], ["--repeat", "513"]):
            with self.subTest(args=args), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ctx:
            main(["--db", "WorkPool/production.sqlite3"])
        self.assertEqual(ctx.exception.code, 2)

    def test_cli_result_schema(self):
        result = io.StringIO()
        with redirect_stdout(result):
            code = main(["--rows", "120", "--repeat", "64"])
        self.assertEqual(code, 0)
        payload = json.loads(result.getvalue())
        self.assertEqual(payload["status"], "PASS_SQLITE_FULL_ROLLBACK")
        self.assertEqual(payload["scope"], "private_tempfile_only_no_workpool")


if __name__ == "__main__":
    unittest.main()
