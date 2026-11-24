"""BL-001 external WorkPool backup leaf alias guard; private fixtures only."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from text_category_profiler.filesystem.legacy import LegacyFileSystem
from text_category_profiler.pipeline.workpool import DeliveryManager
from tests.test_workpool_manager import plan


class WorkIDBackupAliasGuardTests(unittest.TestCase):
    @staticmethod
    def filesystem(calls):
        return LegacyFileSystem(
            make_directory=lambda path: Path(path).mkdir(parents=True, exist_ok=True),
            walk=lambda path: [], chown=lambda path: calls.append(("chown", path)),
            backup=lambda **kw: calls.append(("backup", kw)),
            platform_name=lambda: "Windows",
        )

    def test_normal_workpool_leaf_delegates_exact_existing_path(self):
        with tempfile.TemporaryDirectory() as temp:
            leaf = Path(temp) / "WorkPool" / "job-1"
            leaf.mkdir(parents=True)
            calls = []
            fs = self.filesystem(calls)
            fs.backup(DesDir=str(leaf), BertDatasetSubDir="/private/dataset")
            self.assertEqual(calls, [("backup", {
                "DesDir": str(leaf),
                "BertDatasetSubDir": "/private/dataset",
            })])
            self.assertTrue(leaf.is_dir())

    def test_real_directory_with_trailing_separator_keeps_backend_spelling(self):
        with tempfile.TemporaryDirectory() as temp:
            leaf = Path(temp) / "real"
            leaf.mkdir()
            supplied = str(leaf) + "/"
            calls = []
            self.filesystem(calls).backup(DesDir=supplied)
            self.assertEqual(calls, [("backup", {"DesDir": supplied})])

    def test_existing_file_at_workpool_leaf_is_rejected_before_delegate(self):
        with tempfile.TemporaryDirectory() as temp:
            leaf = Path(temp) / "work-id"
            leaf.write_bytes(b"never-overwrite")
            calls = []
            with self.assertRaisesRegex(
                    RuntimeError, "WORKITEM_BACKUP_DESTINATION_NOT_REAL_DIRECTORY"):
                self.filesystem(calls).backup(DesDir=str(leaf))
            self.assertEqual(calls, [])
            self.assertEqual(leaf.read_bytes(), b"never-overwrite")

    def test_broken_and_valid_symlink_backup_leaf_are_both_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "outside"
            actual.mkdir()
            (actual / "keep.txt").write_bytes(b"not-a-backup-target")
            link = root / "WorkPool-job"
            broken = root / "WorkPool-missing"
            try:
                link.symlink_to(actual, target_is_directory=True)
                broken.symlink_to(root / "does-not-exist", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            calls = []
            fs = self.filesystem(calls)
            for path in (link, broken):
                spellings = (str(path), str(path) + "/", str(path) + "///")
                if os.name == "nt":
                    spellings += (str(path) + "\\",)
                for spelling in spellings:
                    with self.subTest(path=spelling):
                        with self.assertRaisesRegex(
                            RuntimeError, "WORKITEM_BACKUP_DESTINATION_NOT_REAL_DIRECTORY"
                        ):
                            fs.backup(DesDir=spelling)
            self.assertEqual(calls, [])
            self.assertEqual((actual / "keep.txt").read_bytes(), b"not-a-backup-target")
            self.assertTrue(link.is_symlink())
            self.assertTrue(broken.is_symlink())

    def test_external_delivery_fails_before_modifying_alias_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "AutoBertClassify"
            incoming.mkdir()
            pool = root / "WorkPool"
            pool.mkdir()
            actual = root / "outside"
            actual.mkdir()
            (actual / "existing.txt").write_bytes(b"preserved")
            leaf = pool / "private-job"
            try:
                leaf.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            processing = root / "AutoBertClassify_Processing" / "private-job"
            processing.mkdir(parents=True)
            (processing / "input.txt").write_bytes(b"input")
            calls, logs = [], []
            fs = self.filesystem(calls)
            with self.assertRaisesRegex(
                RuntimeError, "WORKITEM_BACKUP_DESTINATION_NOT_REAL_DIRECTORY"
            ):
                DeliveryManager(
                    plan(incoming_path=str(incoming), pool_path=str(pool),
                         work_id="private-job"),
                    fs, output_logger=logs.append,
                ).backup_and_complete(str(root / "private_dataset"))
            self.assertEqual(logs, [])
            self.assertEqual(calls, [])
            self.assertEqual((actual / "existing.txt").read_bytes(), b"preserved")
            self.assertEqual((processing / "input.txt").read_bytes(), b"input")

    def test_missing_destination_retains_legacy_delegate_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "new-output"
            calls = []
            self.filesystem(calls).backup(DesDir=str(target))
            self.assertEqual(calls, [("backup", {"DesDir": str(target)})])
            self.assertFalse(target.exists())

    def test_general_backup_mode_without_desdir_unchanged(self):
        calls = []
        self.filesystem(calls).backup(WorkPoolROOT="/private-workpool",
                                      BertDatasetSubDir="/private-dataset")
        self.assertEqual(calls, [("backup", {
            "WorkPoolROOT": "/private-workpool",
            "BertDatasetSubDir": "/private-dataset",
        })])

    def test_invalid_destination_types_rejected(self):
        calls = []
        for target in ("", "/", "C:\\", "\\\\server\\share\\", None, 5, b"bytes-not-portable"):
            with self.subTest(target=repr(target)):
                with self.assertRaisesRegex(
                        ValueError, "WORKITEM_BACKUP_INVALID_DESTINATION_PATH"):
                    self.filesystem(calls).backup(DesDir=target)
        self.assertEqual(calls, [])

    @unittest.skipUnless(os.name == "nt", "Windows junction fixture")
    def test_windows_junction_backup_leaf_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            actual = Path(temp) / "real"
            actual.mkdir()
            (actual / "keep").write_bytes(b"keep")
            link = Path(temp) / "work-id"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(actual)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("junction unavailable")
            try:
                calls = []
                with self.assertRaisesRegex(
                    RuntimeError, "WORKITEM_BACKUP_DESTINATION_NOT_REAL_DIRECTORY"
                ):
                    self.filesystem(calls).backup(DesDir=str(link))
                self.assertEqual(calls, [])
                self.assertEqual((actual / "keep").read_bytes(), b"keep")
            finally:
                link.rmdir()


if __name__ == "__main__":
    unittest.main()
