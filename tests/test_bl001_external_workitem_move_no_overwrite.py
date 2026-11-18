"""BL-001 external work-ID folder moves: private fixture-only validation."""
import errno
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import text_category_profiler.filesystem.legacy as legacy_fs
import text_category_profiler.filesystem.no_replace as publisher
from text_category_profiler.filesystem.legacy import LegacyFileSystem
from text_category_profiler.pipeline.workpool import (
    WorkPoolManager, DeliveryManager, WorkPoolPlan,
)


class ExternalWorkItemMoveNoOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.original_move = legacy_fs._handoff_rename_noreplace

    def filesystem(self, errors=None):
        return LegacyFileSystem(
            make_directory=lambda path: Path(path).mkdir(parents=True, exist_ok=True),
            walk=lambda _: [], chown=lambda _: None,
            backup=lambda **kw: None,
            platform_name=lambda: "Windows",
        )

    def paths(self, directory):
        root = Path(directory)
        incoming = root / "AutoBertClassify"
        pool = root / "WorkPool"
        processing = root / "AutoBertClassify_Processing"
        processed = root / "AutoBertClassify_Processed"
        for folder in (incoming, pool, processing, processed):
            folder.mkdir()
        work_id = "private-job-01"
        source = incoming / work_id
        source.mkdir()
        (source / "marker.txt").write_bytes(b"private-fixture")
        (pool / work_id).mkdir()
        plan = WorkPoolPlan(
            incoming_path=str(incoming), pool_path=str(pool),
            work_id="", remove_dataset=False, task="",
            workpool_root=str(root / "PrivateWorkPool"),
            output_patterns=("summary.txt",),
        )
        return source, processing / work_id, processed / work_id, plan

    def test_successful_real_manager_move_acquisition_and_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            source, processing, processed, plan = self.paths(directory)
            fs = self.filesystem()
            self.assertEqual(WorkPoolManager(plan, fs).acquire(), "private-job-01")
            self.assertFalse(source.exists())
            self.assertEqual((processing / "marker.txt").read_bytes(), b"private-fixture")
            delivery = plan.with_work_id("private-job-01")
            DeliveryManager(delivery, fs).backup_and_complete(str(Path(directory) / "report"))
            self.assertFalse(processing.exists())
            self.assertEqual((processed / "marker.txt").read_bytes(), b"private-fixture")

    def test_existing_processing_work_item_never_nests_or_merges(self):
        with tempfile.TemporaryDirectory() as directory:
            source, processing, processed, plan = self.paths(directory)
            processing.mkdir()
            (processing / "ctrl-c").write_bytes(b"previous-run")
            with self.assertRaisesRegex(
                FileExistsError, "WORKITEM_MOVE_DESTINATION_ALREADY_EXISTS"
            ):
                WorkPoolManager(plan, self.filesystem()).acquire()
            self.assertEqual((source / "marker.txt").read_bytes(), b"private-fixture")
            self.assertEqual((processing / "ctrl-c").read_bytes(), b"previous-run")
            self.assertFalse((processing / source.name).exists())
            self.assertFalse(processed.exists())

    def test_existing_processed_work_item_cannot_be_nested(self):
        with tempfile.TemporaryDirectory() as directory:
            source, processing, processed, plan = self.paths(directory)
            fs = self.filesystem()
            WorkPoolManager(plan, fs).acquire()
            processed.mkdir()
            (processed / "older").write_bytes(b"preserve")
            reported = []
            DeliveryManager(
                plan.with_work_id(source.name), fs,
                move_error_reporter=reported.append,
            ).backup_and_complete(str(Path(directory) / "report"))
            # The current legacy delivery policy reports and catches errors;
            # this PR protects the filesystem operation itself only.
            self.assertEqual(len(reported), 1)
            self.assertIsInstance(reported[0], FileExistsError)
            self.assertTrue((processing / "marker.txt").is_file())
            self.assertEqual((processed / "older").read_bytes(), b"preserve")
            self.assertFalse((processed / source.name).exists())

    def test_late_competing_destination_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            source, processing, processed, plan = self.paths(directory)
            def competing_rename(src, dst):
                processing.mkdir()
                (processing / "other-owner").write_bytes(b"keep")
                return self.original_move(src, dst)
            with mock.patch.object(legacy_fs, "_handoff_rename_noreplace", competing_rename):
                with self.assertRaises((OSError, FileExistsError)):
                    self.filesystem().move(str(source), str(processing))
            self.assertTrue((source / "marker.txt").is_file())
            self.assertEqual((processing / "other-owner").read_bytes(), b"keep")
            self.assertFalse(processed.exists())

    def test_cross_device_partial_copy_aborts_and_leaves_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            source, processing, processed, plan = self.paths(directory)
            with mock.patch.object(
                legacy_fs, "_handoff_rename_noreplace",
                side_effect=lambda src, dst: shutil.copytree(src, dst),
            ):
                with self.assertRaisesRegex(RuntimeError, "WORKITEM_MOVE_INCOMPLETE"):
                    self.filesystem().move(str(source), str(processing))
            self.assertTrue((source / "marker.txt").is_file())
            self.assertTrue((processing / "marker.txt").is_file())
            self.assertFalse(processed.exists())

    def test_forced_exdev_preserves_nested_and_dangling_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            source, processing, processed, plan = self.paths(directory)
            target = Path(directory) / "outside"
            target.write_bytes(b"external-kept")
            nested = source / "nested-symlink"
            dangling = source / "dangling-symlink"
            try:
                nested.symlink_to(target)
                dangling.symlink_to("missing-target")
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            # Force EXDEV without relying on host mount layout. The production
            # helper must keep links as links, including dangling links.
            fault = OSError(errno.EXDEV, "synthetic cross-volume move")
            if os.name == "nt":
                patcher = mock.patch.object(
                    publisher.os, "rename", side_effect=fault,
                )
            else:
                patcher = mock.patch.object(
                    publisher.ctypes, "CDLL", side_effect=fault,
                )
            with patcher:
                self.assertEqual(
                    self.filesystem().move(str(source), str(processing)),
                    str(processing),
                )
            self.assertFalse(source.exists())
            self.assertTrue((processing / "nested-symlink").is_symlink())
            self.assertTrue((processing / "dangling-symlink").is_symlink())
            self.assertEqual((processing / "nested-symlink").read_bytes(),
                             b"external-kept")
            self.assertEqual(target.read_bytes(), b"external-kept")
            self.assertFalse(processed.exists())

    def test_source_file_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "job"
            destination = root / "completed"
            source.write_bytes(b"file-not-directory")
            with self.assertRaisesRegex(
                FileNotFoundError, "WORKITEM_MOVE_SOURCE_NOT_A_REAL_DIRECTORY"
            ):
                self.filesystem().move(str(source), str(destination))
            self.assertEqual(source.read_bytes(), b"file-not-directory")
            source.unlink()
            actual = root / "real-job"
            actual.mkdir()
            try:
                source.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(FileNotFoundError):
                self.filesystem().move(str(source), str(destination))
            self.assertTrue(source.is_symlink())
            self.assertTrue(actual.is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows junction fixture")
    def test_windows_junction_source_not_moved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actual = root / "real"
            actual.mkdir()
            source = root / "job"
            destination = root / "dest"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source), str(actual)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("junction creation unavailable")
            try:
                with self.assertRaises(FileNotFoundError):
                    self.filesystem().move(str(source), str(destination))
                self.assertTrue(actual.is_dir())
                self.assertFalse(destination.exists())
            finally:
                source.rmdir()


if __name__ == "__main__":
    unittest.main()
