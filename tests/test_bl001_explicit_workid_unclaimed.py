"""Never use a stale explicit Work-ID without a real incoming claim."""
import os
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import WorkPoolManager
from tests.test_workpool_manager import RecordingFileSystem, plan


class ExplicitWorkIDUnclaimedTests(unittest.TestCase):
    @staticmethod
    def fs(incoming, pool):
        return RecordingFileSystem({
            "/jobs/AutoBertClassify": incoming,
            "/jobs/WorkPool": pool,
        })

    def test_unmatched_explicit_id_rejects_without_side_effects(self):
        fs = self.fs(["job-99", "job-20"], ["job-99"])
        log = mock.Mock()
        with self.assertRaisesRegex(
                RuntimeError, "EXTERNAL_WORK_ID_NOT_CLAIMED"):
            WorkPoolManager(
                plan(work_id="job-20"), fs, info=log,
            ).acquire()
        self.assertEqual([x[0] for x in fs.calls], ["list", "list"])
        log.assert_not_called()

    def test_missing_explicit_id_rejects_even_with_newer_matching_candidate(self):
        fs = self.fs(["job-99", "job-20"], ["job-99", "job-20"])
        with self.assertRaisesRegex(
                RuntimeError, "EXTERNAL_WORK_ID_NOT_CLAIMED"):
            WorkPoolManager(plan(work_id="job-10"), fs).acquire()
        self.assertFalse(any(x[0] in ("move", "mkdir", "backup") for x in fs.calls))

    def test_exact_id_still_moves_once(self):
        fs = self.fs(["job-99", "job-20"], ["job-99", "job-20"])
        chosen = WorkPoolManager(plan(work_id="job-20"), fs).acquire()
        self.assertEqual(chosen, "job-20")
        self.assertEqual(len([x for x in fs.calls if x[0] == "move"]), 1)
        self.assertEqual(
            [x for x in fs.calls if x[0] == "move"][0][1],
            os.path.join("/jobs/AutoBertClassify", "job-20"),
        )

    def test_automatic_selection_retains_legacy_latest_candidate(self):
        fs = self.fs(["job-99", "job-20"], ["job-20"])
        self.assertEqual(WorkPoolManager(plan(), fs).acquire(), "job-20")

    def test_no_incoming_candidates_still_abort_before_pool_list(self):
        fs = self.fs([], ["job-20"])
        with self.assertRaises(Exception):
            WorkPoolManager(plan(work_id="job-20"), fs).acquire()
        self.assertEqual(len([x for x in fs.calls if x[0] == "list"]), 1)


if __name__ == "__main__":
    unittest.main()
