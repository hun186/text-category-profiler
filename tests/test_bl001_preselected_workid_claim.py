"""BL-001 explicit Work-ID cannot silently claim another queued job."""
import os
import unittest

from text_category_profiler.pipeline.workpool import WorkPoolManager
from tests.test_workpool_manager import RecordingFileSystem, plan


INCOMING = "/jobs/AutoBertClassify"
POOL = "/jobs/WorkPool"


class ExplicitWorkIDAcquisitionTests(unittest.TestCase):
    @staticmethod
    def fs(incoming, pool):
        return RecordingFileSystem({
            INCOMING: incoming, POOL: pool,
        })

    def test_explicit_selection_claims_only_requested_id_not_newest(self):
        fs = self.fs(["job-900", "job-001"], ["job-900", "job-001"])
        chosen = WorkPoolManager(plan(work_id="job-001"), fs).acquire()
        self.assertEqual(chosen, "job-001")
        moves = [x for x in fs.calls if x[0] == "move"]
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0][1], os.path.join(INCOMING, "job-001"))
        self.assertTrue(moves[0][2].endswith(os.path.join(
            "AutoBertClassify_Processing", "job-001"
        )))

    def test_unselected_candidate_is_never_moved_even_if_only_eligible(self):
        fs = self.fs(["job-900", "job-001"], ["job-900"])
        chosen = WorkPoolManager(plan(work_id="job-001"), fs).acquire()
        # Preserve the existing preselected/no-claim mode rather than
        # silently claiming a different work item.
        self.assertEqual(chosen, "job-001")
        self.assertEqual([x for x in fs.calls if x[0] in ("mkdir", "move")], [])

    def test_blank_selection_preserves_latest_matched_id(self):
        fs = self.fs(["job-001", "job-900"], ["job-001", "job-900"])
        chosen = WorkPoolManager(plan(), fs).acquire()
        self.assertEqual(chosen, "job-900")
        moves = [x for x in fs.calls if x[0] == "move"]
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0][1], os.path.join(INCOMING, "job-900"))

    def test_unicode_named_work_selected_without_normalization(self):
        name = "中文 工作單 2026"
        fs = self.fs([name, "job-900"], [name, "job-900"])
        self.assertEqual(WorkPoolManager(
            plan(work_id=name), fs,
        ).acquire(), name)
        self.assertEqual(
            [x for x in fs.calls if x[0] == "move"][0][1],
            os.path.join(INCOMING, name),
        )

    def test_invalid_preselected_name_fails_before_list_directory(self):
        fs = self.fs(["job-900"], ["job-900"])
        with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
            WorkPoolManager(plan(work_id="COM1 .txt"), fs).acquire()
        self.assertEqual(fs.calls, [])

    def test_no_candidate_preserves_existing_abort_behavior(self):
        fs = self.fs([], [])
        with self.assertRaises(Exception):
            WorkPoolManager(plan(work_id="job-001"), fs).acquire()
        self.assertEqual([c[0] for c in fs.calls], ["list"])


if __name__ == "__main__":
    unittest.main()
