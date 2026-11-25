"""Configured external auto WorkPool mode must never silently run no job."""
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import WorkPoolManager
from tests.test_workpool_manager import RecordingFileSystem, plan


class WorkPoolNoMatchFailStopTests(unittest.TestCase):
    @staticmethod
    def fs(incoming, pool):
        return RecordingFileSystem({
            "/jobs/AutoBertClassify": incoming,
            "/jobs/WorkPool": pool,
        })

    def test_no_matching_work_id_prevents_any_processing_move(self):
        fs = self.fs(["candidate-A"], ["candidate-B"])
        info = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "EXTERNAL_WORKPOOL_NO_MATCH"):
            WorkPoolManager(plan(), fs, info=info).acquire()
        self.assertEqual([call[0] for call in fs.calls], ["list", "list"])
        info.assert_not_called()

    def test_empty_workpool_inventory_with_nonempty_incoming_aborts(self):
        fs = self.fs(["candidate-A", "candidate-B"], [])
        with self.assertRaisesRegex(RuntimeError, "EXTERNAL_WORKPOOL_NO_MATCH"):
            WorkPoolManager(plan(), fs).acquire()
        self.assertFalse(any(x[0] in ("mkdir", "move", "backup")
                             for x in fs.calls))

    def test_matching_candidate_still_claims_latest_compatible_job(self):
        fs = self.fs(["job-9", "job-2", "job-1"], ["job-1", "job-2"])
        self.assertEqual(WorkPoolManager(plan(), fs).acquire(), "job-2")
        self.assertEqual([x[0] for x in fs.calls].count("move"), 1)

    def test_explicit_id_no_match_retains_different_fatal_code(self):
        fs = self.fs(["job-9"], ["job-9"])
        with self.assertRaisesRegex(RuntimeError, "EXTERNAL_WORK_ID_NOT_CLAIMED"):
            WorkPoolManager(plan(work_id="job-1"), fs).acquire()

    def test_no_incoming_candidates_keep_legacy_abort_path(self):
        fs = self.fs([], ["job-1"])
        with self.assertRaises(Exception):
            WorkPoolManager(plan(), fs).acquire()
        self.assertEqual([x[0] for x in fs.calls], ["list"])


if __name__ == "__main__":
    unittest.main()
