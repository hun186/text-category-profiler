"""Known completion conflicts must stop before any backup or cleanup."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from text_category_profiler.filesystem.legacy import LegacyFileSystem
from text_category_profiler.pipeline.workpool import DeliveryManager
from tests import test_bl001_delivery_source_preflight as source_fixtures


class DeliveryDestinationPreflightTests(unittest.TestCase):
    def fixture(self, root):
        backups = []
        plan, fs, source = source_fixtures.WorkItemDeliverySourcePreflightTests.fixture(
            root, backups=backups, remove=True)
        source.mkdir(parents=True)
        (source / "keep").write_bytes(b"current")
        completed = root / "AutoBertClassify_Processed" / plan.work_id
        completed.parent.mkdir()
        fs._chown = mock.Mock()
        fs._walk = mock.Mock()
        fs._platform_name = lambda: "Linux"
        return plan, fs, source, completed, backups

    def assert_collision(self, plan, fs, source, backups):
        log = mock.Mock()
        reporter = mock.Mock(side_effect=OSError("logger broken"))
        with self.assertRaisesRegex(
                FileExistsError, "WORKITEM_MOVE_DESTINATION_ALREADY_EXISTS"):
            DeliveryManager(plan, fs, output_logger=log,
                            move_error_reporter=reporter).backup_and_complete("/fixture")
        self.assertEqual(backups, [])
        self.assertEqual((source / "keep").read_bytes(), b"current")
        fs._chown.assert_not_called()
        fs._walk.assert_not_called()
        log.assert_not_called()
        reporter.assert_called_once()

    def test_existing_directory_or_file_blocks_all_backups(self):
        for is_directory in (True, False):
            with self.subTest(is_directory=is_directory), tempfile.TemporaryDirectory() as tmp:
                plan, fs, source, completed, backups = self.fixture(Path(tmp))
                if is_directory:
                    completed.mkdir()
                    marker = completed / "previous"
                else:
                    marker = completed
                marker.write_bytes(b"older")
                self.assert_collision(plan, fs, source, backups)
                self.assertEqual(marker.read_bytes(), b"older")

    def test_dangling_link_blocks_all_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, fs, source, completed, backups = self.fixture(root)
            try:
                completed.symlink_to(root / "absent", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            self.assert_collision(plan, fs, source, backups)
            self.assertTrue(completed.is_symlink())

    def test_unreadable_destination_does_not_count_as_absent(self):
        fs = LegacyFileSystem(make_directory=mock.Mock(), walk=mock.Mock(),
                              chown=mock.Mock(), backup=mock.Mock())
        with mock.patch("text_category_profiler.filesystem.legacy.os.lstat",
                        side_effect=PermissionError("denied")):
            with self.assertRaises(PermissionError):
                fs.verify_delivery_destination_absent("/fixture")

    def test_late_collision_still_rejected_by_exclusive_move(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan, fs, source, completed, backups = self.fixture(Path(tmp))
            def backup(**kw):
                backups.append(kw)
                if "DesDir" in kw:
                    completed.mkdir()
                    (completed / "other").write_bytes(b"other")
            fs._backup = backup
            log = mock.Mock()
            with self.assertRaisesRegex(
                    FileExistsError, "WORKITEM_MOVE_DESTINATION_ALREADY_EXISTS"):
                DeliveryManager(plan, fs, output_logger=log,
                                move_error_reporter=lambda error: None).backup_and_complete("/fixture")
            self.assertEqual(len(backups), 2)
            self.assertEqual((completed / "other").read_bytes(), b"other")
            self.assertEqual((source / "keep").read_bytes(), b"current")
            fs._walk.assert_not_called()
            log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
