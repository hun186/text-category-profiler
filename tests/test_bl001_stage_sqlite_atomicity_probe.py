"""Private SQLite writer-interruption diagnostic: classify real crash outcome.

These tests certify the PROBE, not the stage writer's atomicity. An expected
FAIL_ATOMICITY result for the existing two-step writer must remain visible.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest

from scripts.bl001_stage_sqlite_atomicity_probe import main, run_probe


ROOT = Path(__file__).resolve().parents[1]


class SQLiteAtomicityProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas is required for this real-process probe")

    def test_probe_reports_incomplete_or_safe_write_with_private_files(self):
        pool = ROOT / "WorkPool"
        before = tuple(sorted(path.name for path in pool.iterdir())) if pool.is_dir() else ()
        result = run_probe()
        self.assertEqual(result["scope"], "private_tempfile_only_no_workpool")
        self.assertEqual(result["interruption"], "writer_killed_after_replace_before_index")
        self.assertEqual(result["integrity_check"], "ok")
        self.assertIn(result["status"], {"FAIL_ATOMICITY", "PASS_ATOMICITY"})
        if result["status"] == "FAIL_ATOMICITY":
            self.assertFalse(result["original_preserved"])
        else:
            self.assertTrue(result["original_preserved"])
            self.assertFalse(result["new_partial_rows_present"])
            self.assertTrue(result["text_index_present"])
        after = tuple(sorted(path.name for path in pool.iterdir())) if pool.is_dir() else ()
        self.assertEqual(before, after)

    def test_cli_exit_is_nonzero_on_atomicity_gap_and_rejects_external_db_paths(self):
        output = io.StringIO()
        with redirect_stdout(output):
            rc = main([])
        result = json.loads(output.getvalue())
        self.assertIn(result["status"], {"FAIL_ATOMICITY", "PASS_ATOMICITY"})
        self.assertEqual(rc, 0 if result["status"] == "PASS_ATOMICITY" else 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--db", str(ROOT / "WorkPool" / "production.sqlite3")])
        self.assertEqual(raised.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
