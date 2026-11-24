"""Post-claim info callbacks cannot make a committed Work-ID claim fail."""
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import WorkPoolManager
from tests.test_workpool_manager import RecordingFileSystem, plan


class WorkPoolPostClaimInfoTests(unittest.TestCase):
    @staticmethod
    def fs():
        return RecordingFileSystem({
            "/jobs/AutoBertClassify": ["job-1"],
            "/jobs/WorkPool": ["job-1"],
        })

    def test_info_failure_after_successful_move_keeps_claimed_id(self):
        fs = self.fs()
        info = mock.Mock(side_effect=OSError("log disk unavailable"))
        selected = WorkPoolManager(plan(), fs, info=info).acquire()
        self.assertEqual(selected, "job-1")
        self.assertEqual([x[0] for x in fs.calls].count("move"), 1)
        info.assert_called_once()

    def test_broken_info_callback_does_not_replay_or_drop_claim(self):
        fs = self.fs()
        cb = mock.Mock(side_effect=RuntimeError("broken reporter"))
        result = WorkPoolManager(
            plan(work_id="job-1"), fs, info=cb,
        ).acquire()
        self.assertEqual(result, "job-1")
        self.assertEqual([x[0] for x in fs.calls].count("move"), 1)

    def test_failed_exclusive_move_is_not_hidden_by_reporting_boundary(self):
        failure = FileExistsError("existing processing job")
        fs = RecordingFileSystem({
            "/jobs/AutoBertClassify": ["job-1"],
            "/jobs/WorkPool": ["job-1"],
        }, move_error=failure)
        info = mock.Mock(side_effect=ValueError("would mask failure"))
        with self.assertRaises(FileExistsError) as caught:
            WorkPoolManager(plan(), fs, info=info).acquire()
        self.assertIs(caught.exception, failure)
        info.assert_not_called()
        self.assertEqual([x[0] for x in fs.calls].count("move"), 1)

    def test_successful_info_callback_still_sees_original_message(self):
        fs = self.fs()
        messages = []
        self.assertEqual(
            WorkPoolManager(plan(), fs, info=messages.append).acquire(),
            "job-1",
        )
        self.assertEqual(len(messages), 1)
        self.assertIn("Found workID job-1", messages[0])


if __name__ == "__main__":
    unittest.main()
