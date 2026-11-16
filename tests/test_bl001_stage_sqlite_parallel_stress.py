"""Private-process SQLite stress acceptance and hard-bound regression."""
from contextlib import redirect_stdout
import io
import json
import unittest
from scripts.bl001_stage_sqlite_parallel_stress import main, stress_private_writers


class PrivateParallelStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas needed")

    def test_two_concurrent_processes_publish_only_complete_rows(self):
        report = stress_private_writers(workers=2, rounds=1, rows=10)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["scope"], "private_tempfile_only_no_workpool")
        self.assertEqual(len(report["completed_rounds"]), 1)
        result = report["completed_rounds"][0]
        self.assertGreaterEqual(result["committed"], 1)
        self.assertEqual(result["committed"] + result["locked"], 2)

    def test_reject_unbounded_and_external_database_inputs(self):
        for args in (["--workers", "8"], ["--rounds", "5"],
                     ["--rows", "100000"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as err:
            main(["--db", "WorkPool/production.sqlite3"])
        self.assertEqual(err.exception.code, 2)

    def test_cli_json_reports_one_small_round(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--workers", "2", "--rounds", "1", "--rows", "5"])
        self.assertEqual(code, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
