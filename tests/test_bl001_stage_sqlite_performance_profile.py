"""KI-012 bounded private SQLite performance-instrument correctness tests."""
from contextlib import redirect_stdout
import io
import json
import unittest

from scripts.bl001_stage_sqlite_performance_profile import (
    main,
    profile_private_writers,
)


class PrivatePerformanceProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas is required")

    def test_small_private_profile_is_complete_and_bounded(self):
        report = profile_private_writers(rows=40, rounds=2)
        self.assertEqual(report["status"], "PASS_MEASURED")
        self.assertEqual(report["scope"], "private_tempfile_only_no_workpool")
        self.assertEqual(report["rows"], 40)
        self.assertEqual(report["rounds"], 2)
        self.assertEqual(set(report["elapsed_seconds"]), {
            "legacy_two_step", "atomic_staging",
        })
        for kind, values in report["elapsed_seconds"].items():
            self.assertEqual(len(values), 2, kind)
            self.assertTrue(all(time >= 0 for time in values))
            self.assertGreater(report["db_file_bytes"][kind], 100)
        self.assertGreaterEqual(report["atomic_vs_legacy_elapsed_ratio"], 0)

    def test_refuses_unbounded_or_external_path_arguments(self):
        for args in (
            ["--rows", "20001"], ["--rows", "0"],
            ["--rounds", "0"], ["--rounds", "4"],
        ):
            with self.subTest(args=args):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as err:
            main(["--db", "WorkPool/private.sqlite3"])
        self.assertEqual(err.exception.code, 2)

    def test_small_cli_has_json_and_success_exit(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--rows", "25", "--rounds", "1"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PASS_MEASURED")


if __name__ == "__main__":
    unittest.main()
