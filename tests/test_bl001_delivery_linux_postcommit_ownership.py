"""Linux delivery ownership must never touch a competing completed item.

Only fake filesystem ports are used; no real WorkPool, chown or UID changes.
"""
import os
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import DeliveryManager
from tests.test_workpool_manager import RecordingFileSystem, plan


class PostCommitOwnershipTests(unittest.TestCase):
    @staticmethod
    def make_fs(*, move_error=None):
        return RecordingFileSystem(system="Linux", move_error=move_error)

    def test_completed_descendants_are_chowned_only_after_move_commits(self):
        fs = self.make_fs()
        observed = []
        original_walk = fs.walk

        def walk(path):
            observed.append("walk")
            moves = [call for call in fs.calls if call[0] == "move"]
            self.assertEqual(len(moves), 1)
            self.assertEqual(path, moves[0][2])
            return original_walk(path)

        fs.walk = walk
        successes = []
        DeliveryManager(
            plan(work_id="job-1"), fs, output_logger=successes.append,
        ).backup_and_complete("/private-dataset")
        self.assertEqual(observed, ["walk"])
        self.assertEqual(len(successes), 1)
        calls = fs.calls
        index_move = next(i for i, x in enumerate(calls) if x[0] == "move")
        index_walk = next(i for i, x in enumerate(calls) if x[0] == "walk")
        self.assertLess(index_move, index_walk)
        index_mkdir = next(i for i, x in enumerate(calls) if x[0] == "mkdir")
        first_chown = next(i for i, x in enumerate(calls) if x[0] == "chown")
        self.assertLess(index_mkdir, first_chown)

    def test_failed_exclusive_move_never_walks_or_chowns_old_target(self):
        collision = FileExistsError("someone else already completed it")
        fs = self.make_fs(move_error=collision)
        fs.walk = mock.Mock(side_effect=AssertionError(
            "must not visit preexisting completed job"))
        reporter, complete = mock.Mock(), mock.Mock()
        with self.assertRaises(FileExistsError) as raised:
            DeliveryManager(
                plan(work_id="job-1"), fs, output_logger=complete,
                move_error_reporter=reporter,
            ).backup_and_complete("/private-dataset")
        self.assertIs(raised.exception, collision)
        reporter.assert_called_once_with(collision)
        complete.assert_not_called()
        fs.walk.assert_not_called()
        target = os.path.join(
            "/jobs/AutoBertClassify", "..", "AutoBertClassify_Processed", "job-1")
        self.assertNotIn(("chown", target), fs.calls)
        self.assertFalse(any(x[0] == "chown" and x[1].startswith(target + os.sep)
                             for x in fs.calls))

    def test_postcommit_chown_failure_does_not_replay_nonidempotent_move(self):
        fs = self.make_fs()
        original_chown = fs.chown
        problem = PermissionError("chown after commit unavailable")

        def chown(path):
            if path.endswith("artifact.tsv"):
                raise problem
            return original_chown(path)

        fs.chown = chown
        reported, delivered = [], []
        DeliveryManager(
            plan(work_id="job-1"), fs, output_logger=delivered.append,
            move_error_reporter=reported.append,
        ).backup_and_complete("/private-dataset")
        self.assertEqual(reported, [problem])
        self.assertEqual(len(delivered), 1)
        self.assertEqual([c[0] for c in fs.calls].count("move"), 1)

    def test_postcommit_walk_error_and_reporter_fault_still_no_replay(self):
        fs = self.make_fs()
        problem = OSError("cannot walk completed job")
        fs.walk = mock.Mock(side_effect=problem)
        reported = mock.Mock(side_effect=RuntimeError("reporter unavailable"))
        delivered = mock.Mock()
        DeliveryManager(
            plan(work_id="job-1"), fs,
            output_logger=delivered, move_error_reporter=reported,
        ).backup_and_complete("/private-dataset")
        reported.assert_called_once_with(problem)
        delivered.assert_called_once()
        self.assertEqual([c[0] for c in fs.calls].count("move"), 1)

    def test_nonlinux_delivery_still_never_walks_or_chowns(self):
        fs = RecordingFileSystem(system="Windows")
        DeliveryManager(plan(work_id="job-1"), fs).backup_and_complete(
            "/private-dataset"
        )
        self.assertFalse(any(c[0] in ("chown", "walk") for c in fs.calls))
        self.assertEqual([c[0] for c in fs.calls].count("move"), 1)


if __name__ == "__main__":
    unittest.main()
