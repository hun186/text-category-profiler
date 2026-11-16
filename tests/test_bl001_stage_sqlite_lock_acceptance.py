"""Real private disk SQLite lock/recovery checks, including a separate process.

The CLI test never accepts a WorkPool/SQLite path and uses tempfiles only.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from scripts.bl001_stage_sqlite_lock_acceptance import (
    main,
    run_private_lock_acceptance,
)


ROOT = Path(__file__).resolve().parents[1]


class PrivateSQLiteLockAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas is required for the real SQLite lock test")

    def test_private_writer_is_locked_then_recovers_after_graceful_and_abrupt_release(self):
        default_pool = ROOT / "WorkPool"
        before = tuple(sorted(entry.name for entry in default_pool.iterdir())) if default_pool.is_dir() else ()
        result = run_private_lock_acceptance()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["scope"], "private_tempfile_only_no_workpool")
        self.assertEqual(result["checks"], [
            "initial_write_and_index",
            "graceful_unlock_rejects_write_and_preserves_rows",
            "graceful_unlock_retry_and_index",
            "terminated_lock_holder_rejects_write_and_preserves_rows",
            "terminated_lock_holder_retry_and_index",
        ])
        after = tuple(sorted(entry.name for entry in default_pool.iterdir())) if default_pool.is_dir() else ()
        self.assertEqual(after, before)

    def test_one_click_cli_reports_json_pass_without_external_database_argument(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main([])
        self.assertEqual(code, 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["status"], "PASS")
        self.assertIn("no_workpool", result["scope"])
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--db", str(ROOT / "WorkPool" / "unsafe.sqlite3")])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
