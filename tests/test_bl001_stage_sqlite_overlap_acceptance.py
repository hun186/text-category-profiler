"""KI-012 private overlap and orphan-preservation acceptance.

Test purpose: real process interleavings and locks on disposable sqlite files.
This is NOT a live WorkPool test or permission to remove orphan tables.
"""
from contextlib import redirect_stdout
import io
from pathlib import Path
import unittest

from scripts.bl001_stage_sqlite_overlap_acceptance import (
    main,
    run_private_overlap_acceptance,
)

ROOT = Path(__file__).resolve().parents[1]


class PrivateSQLiteOverlapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas required for actual SQLite writer/processes")

    def test_two_private_process_interleavings_preserve_committed_rows_and_indexes(self):
        # The diagnostic itself can allocate only TemporaryDirectory databases
        # and has no path parameter or WorkPool mutation entrypoint.
        result = run_private_overlap_acceptance()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["scope"], "private_tempfile_only_no_workpool")
        self.assertEqual(result["checks"], [
            "overlap_before_swap_other_writer_commits",
            "killed_pre_swap_preserves_winner_and_reports_candidate",
            "subsequent_writer_does_not_delete_unowned_candidate",
            "overlap_inside_swap_competing_writer_rejected",
            "killed_mid_swap_rolls_back_sampleSrc_and_index",
            "post_rollback_retry_preserves_existing_candidate",
        ])
        self.assertEqual(result["orphan_candidates_after_pre_swap_kill"], 1)
        self.assertEqual(result["orphan_candidates_after_mid_swap_kill"], 1)

    def test_cli_rejects_database_paths_instead_of_touching_user_workpool(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            main(["--db", str(ROOT / "WorkPool" / "existing.sql3")])
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(out.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
