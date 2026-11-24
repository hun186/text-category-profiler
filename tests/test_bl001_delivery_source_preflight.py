"""A missing/aliased Processing work item cannot trigger report backups."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from text_category_profiler.filesystem.legacy import LegacyFileSystem
from text_category_profiler.pipeline.workpool import DeliveryManager, WorkPoolPlan


class WorkItemDeliverySourcePreflightTests(unittest.TestCase):
    @staticmethod
    def fixture(root, *, backups, work_id="job-01", remove=True):
        incoming, pool = root / "AutoBertClassify", root / "WorkPool"
        incoming.mkdir(exist_ok=True)
        pool.mkdir(exist_ok=True)
        plan = WorkPoolPlan(
            incoming_path=str(incoming), pool_path=str(pool),
            work_id=work_id, remove_dataset=remove, task="",
            workpool_root=str(pool), output_patterns=("result.tsv",),
        )
        fs = LegacyFileSystem(
            make_directory=lambda path: Path(path).mkdir(parents=True, exist_ok=True),
            walk=lambda path: [], chown=lambda path: None,
            backup=lambda **kw: backups.append(kw),
            platform_name=lambda: "Windows",
        )
        source = root / "AutoBertClassify_Processing" / work_id
        return plan, fs, source

    def test_absent_processing_job_aborts_before_any_backup_or_completed_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = []
            plan, fs, source = self.fixture(root, backups=backups)
            delivered = mock.Mock()
            with self.assertRaisesRegex(
                    FileNotFoundError,
                    "WORKITEM_DELIVERY_SOURCE_NOT_REAL_DIRECTORY"):
                DeliveryManager(
                    plan, fs, output_logger=delivered
                ).backup_and_complete(str(root / "dataset"))
            self.assertEqual(backups, [])
            self.assertFalse(source.exists())
            self.assertFalse((root / "AutoBertClassify_Processed").exists())
            delivered.assert_not_called()

    def test_file_like_processing_source_aborts_without_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = []
            plan, fs, source = self.fixture(root, backups=backups)
            source.parent.mkdir(parents=True)
            source.write_bytes(b"not a directory")
            with self.assertRaisesRegex(FileNotFoundError, "WORKITEM_DELIVERY_SOURCE"):
                DeliveryManager(plan, fs).backup_and_complete(str(root / "dataset"))
            self.assertEqual(backups, [])
            self.assertEqual(source.read_bytes(), b"not a directory")

    def test_processing_symlink_never_writes_backup_even_when_target_is_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = []
            plan, fs, source = self.fixture(root, backups=backups)
            source.parent.mkdir(parents=True)
            target = root / "unrelated-live-job"
            target.mkdir()
            (target / "keep").write_bytes(b"private")
            try:
                source.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation not permitted on host")
            with self.assertRaisesRegex(FileNotFoundError, "WORKITEM_DELIVERY_SOURCE"):
                DeliveryManager(plan, fs).backup_and_complete(str(root / "dataset"))
            self.assertTrue(source.is_symlink())
            self.assertEqual((target / "keep").read_bytes(), b"private")
            self.assertEqual(backups, [])

    def test_real_claimed_processing_source_retains_backup_then_move_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = []
            plan, fs, source = self.fixture(root, backups=backups)
            source.mkdir(parents=True)
            (source / "owned").write_bytes(b"this-run")
            recorded = []
            def backup(**kw):
                self.assertTrue(source.is_dir())
                recorded.append(("backup", kw))
            fs._backup = backup
            result = DeliveryManager(
                plan, fs, output_logger=lambda message: recorded.append(("complete", message))
            ).backup_and_complete(str(root / "dataset"))
            dest = root / "AutoBertClassify_Processed" / "job-01"
            self.assertIsNone(result)
            self.assertFalse(source.exists())
            self.assertEqual((dest / "owned").read_bytes(), b"this-run")
            self.assertEqual([x[0] for x in recorded],
                             ["backup", "backup", "complete"])

    def test_empty_id_preserves_optional_nonjob_cleanup_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            backups = []
            plan, fs, _ = self.fixture(
                root, backups=backups, work_id="", remove=True)
            DeliveryManager(plan, fs).backup_and_complete(str(root / "dataset"))
            self.assertEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
