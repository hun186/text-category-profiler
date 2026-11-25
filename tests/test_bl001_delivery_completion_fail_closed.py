"""BL-001: private Work-ID delivery completion cannot claim false success."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from text_category_profiler.filesystem.legacy import LegacyFileSystem
from text_category_profiler.pipeline.workpool import DeliveryManager, WorkPoolPlan
from tests.test_workpool_manager import RecordingFileSystem, plan


class DeliveryCompletionFailClosedTests(unittest.TestCase):
    @staticmethod
    def private_plan(root, work_id="private-job-01"):
        return WorkPoolPlan(
            incoming_path=str(root / "AutoBertClassify"),
            pool_path=str(root / "WorkPool"),
            work_id=work_id, remove_dataset=False, task="",
            workpool_root=str(root / "WorkPool"),
            output_patterns=("test.sql3",),
        )

    @staticmethod
    def private_fs(backups):
        return LegacyFileSystem(
            make_directory=lambda p: Path(p).mkdir(parents=True, exist_ok=True),
            walk=lambda p: [], chown=lambda p: None,
            backup=lambda **kw: backups.append(kw),
            platform_name=lambda: "Windows",
        )

    def test_success_log_emitted_after_completed_directory_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "AutoBertClassify"
            processing = root / "AutoBertClassify_Processing" / "private-job-01"
            processed = root / "AutoBertClassify_Processed" / "private-job-01"
            incoming.mkdir()
            processing.mkdir(parents=True)
            (processing / "marker.txt").write_bytes(b"private")
            backups = []
            events = []
            def log(message):
                self.assertTrue(processed.is_dir())
                self.assertFalse(processing.exists())
                self.assertEqual((processed / "marker.txt").read_bytes(), b"private")
                events.append(message)
            DeliveryManager(
                self.private_plan(root), self.private_fs(backups),
                output_logger=log,
            ).backup_and_complete(str(root / "output"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(len(events), 1)
            self.assertIn("Complete ", events[0])

    def test_collision_keeps_both_work_id_folders_and_raises(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "AutoBertClassify"
            incoming.mkdir()
            processing = root / "AutoBertClassify_Processing" / "private-job-01"
            processing.mkdir(parents=True)
            (processing / "marker.txt").write_bytes(b"current")
            processed = root / "AutoBertClassify_Processed" / "private-job-01"
            processed.mkdir(parents=True)
            (processed / "ctrl-c-leftover.txt").write_bytes(b"previous")
            events, reported, backups = [], [], []
            with self.assertRaisesRegex(
                FileExistsError, "WORKITEM_MOVE_DESTINATION_ALREADY_EXISTS"
            ):
                DeliveryManager(
                    self.private_plan(root), self.private_fs(backups),
                    output_logger=events.append,
                    move_error_reporter=reported.append,
                ).backup_and_complete(str(root / "output"))
            self.assertEqual(len(backups), 0)
            self.assertEqual(len(reported), 1)
            self.assertIsInstance(reported[0], FileExistsError)
            self.assertEqual(events, [])
            self.assertEqual((processing / "marker.txt").read_bytes(), b"current")
            self.assertEqual((processed / "ctrl-c-leftover.txt").read_bytes(), b"previous")
            self.assertFalse((processed / "private-job-01").exists())

    def test_reporter_fault_never_masks_original_move_failure(self):
        move_failure = OSError("original move failed")
        fake = RecordingFileSystem(move_error=move_failure)
        on_success = mock.Mock()
        reporter = mock.Mock(side_effect=RuntimeError("reporter broken"))
        with self.assertRaises(OSError) as raised:
            DeliveryManager(
                plan(work_id="job-1"), fake,
                output_logger=on_success, move_error_reporter=reporter,
            ).backup_and_complete("/private")
        self.assertIs(raised.exception, move_failure)
        on_success.assert_not_called()
        reporter.assert_called_once_with(move_failure)

    def test_post_commit_logger_failure_does_not_replay_move(self):
        fake = RecordingFileSystem()
        failure = OSError("completion log unavailable")
        reporter = mock.Mock()
        complete_log = mock.Mock(side_effect=failure)
        DeliveryManager(
            plan(work_id="job-1"), fake,
            output_logger=complete_log, move_error_reporter=reporter,
        ).backup_and_complete("/private")
        moves = [call for call in fake.calls if call[0] == "move"]
        self.assertEqual(len(moves), 1)
        complete_log.assert_called_once()
        reporter.assert_called_once_with(failure)

    def test_reporter_fault_after_successful_move_does_not_undo_commit(self):
        fake = RecordingFileSystem()
        reporter = mock.Mock(side_effect=RuntimeError("reporter failed"))
        complete_log = mock.Mock(side_effect=OSError("log failed"))
        DeliveryManager(
            plan(work_id="job-1"), fake,
            output_logger=complete_log, move_error_reporter=reporter,
        ).backup_and_complete("/private")
        self.assertEqual(len([x for x in fake.calls if x[0] == "move"]), 1)
        reporter.assert_called_once()

    def test_no_external_work_id_skips_delivery_move_and_success_message(self):
        fake = RecordingFileSystem()
        on_success = mock.Mock()
        DeliveryManager(
            plan(work_id=""), fake, output_logger=on_success,
        ).backup_and_complete("/private")
        self.assertFalse(any(c[0] == "move" for c in fake.calls))
        on_success.assert_not_called()

    def test_backup_failure_does_not_log_completion_or_move(self):
        error = OSError("backup unavailable")
        fake = RecordingFileSystem(backup_error=error)
        logger = mock.Mock()
        with self.assertRaises(OSError) as caught:
            DeliveryManager(
                plan(work_id="job-1"), fake, output_logger=logger,
            ).backup_and_complete("/private")
        self.assertIs(caught.exception, error)
        self.assertFalse(any(c[0] == "move" for c in fake.calls))
        logger.assert_not_called()


if __name__ == "__main__":
    unittest.main()
