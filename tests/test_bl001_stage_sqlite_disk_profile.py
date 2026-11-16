"""KI-012 disk-stage instrumentation tests: all private temp files."""
import io
import json
from contextlib import redirect_stdout
import unittest

from scripts.bl001_stage_sqlite_disk_profile import (
    main, profile_private_disk,
)


class PrivateDiskCheckpointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas required")

    def test_stage_snapshots_preserve_schema_and_measure_sidecars(self):
        result = profile_private_disk(rows=25, repeat=2)
        self.assertEqual(result["status"], "PASS_CHECKPOINT_MEASURED")
        self.assertFalse(result["production_workpool_verified"])
        self.assertEqual(result["scope"], "private_tempfile_only_no_workpool")
        phases = result["phase_disk_bytes"]
        labels = {x["stage"] for x in phases}
        self.assertTrue({"candidate_ready", "after_copy", "after_text_index",
                         "before_swap_commit", "closed_final"} <= labels)
        for snapshot in [result["initial_disk_bytes"], *phases]:
            self.assertEqual(snapshot["total"], sum(
                snapshot[key] for key in ("db", "journal", "wal", "shm")
            ))
            self.assertGreater(snapshot["db"], 0)
            self.assertTrue(all(snapshot[key] >= 0 for key in
                                ("db", "journal", "wal", "shm", "total")))
        self.assertGreaterEqual(
            result["checkpoint_max_total_bytes"],
            result["closed_final_total_bytes"],
        )

    def test_cli_bounds_and_production_path_rejection(self):
        for args in (["--rows", "9"], ["--rows", "20001"],
                     ["--repeat", "0"], ["--repeat", "9"]):
            with self.subTest(args=args), redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as ex:
            main(["--db", "WorkPool/prod.sqlite3"])
        self.assertEqual(ex.exception.code, 2)

    def test_cli_json_reports_private_only(self):
        out = io.StringIO()
        with redirect_stdout(out):
            exit_code = main(["--rows", "10", "--repeat", "1"])
        self.assertEqual(exit_code, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "PASS_CHECKPOINT_MEASURED")
        self.assertFalse(report["production_workpool_verified"])


if __name__ == "__main__":
    unittest.main()
