"""Reject a bogus selected WorkPool input before incoming claim."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from text_category_profiler.filesystem.legacy import LegacyFileSystem
from text_category_profiler.pipeline.workpool import WorkPoolManager, WorkPoolPlan


class AcquisitionPoolLeafTests(unittest.TestCase):
    def fixture(self, root, work_id=""):
        incoming = root / "AutoBertClassify"
        pool = root / "WorkPool"
        incoming.mkdir()
        pool.mkdir()
        for name in ("job-1", "job-9"):
            (incoming / name).mkdir()
            (incoming / name / "keep").write_bytes(b"incoming")
        (pool / "job-1").mkdir()
        plan = WorkPoolPlan(str(incoming), str(pool), work_id, False, "",
                            str(pool), ())
        fs = LegacyFileSystem(
            make_directory=lambda path: Path(path).mkdir(parents=True, exist_ok=True),
            walk=lambda path: [], chown=lambda path: None,
            backup=mock.Mock(), platform_name=lambda: "Windows",
        )
        return plan, fs, incoming, pool

    def assert_rejected(self, root, plan, fs, incoming):
        info = mock.Mock()
        with self.assertRaisesRegex(
                FileNotFoundError, "WORKITEM_ACQUISITION_POOL_NOT_REAL_DIRECTORY"):
            WorkPoolManager(plan, fs, info=info).acquire()
        for name in ("job-1", "job-9"):
            self.assertEqual((incoming / name / "keep").read_bytes(), b"incoming")
        self.assertFalse((root / "AutoBertClassify_Processing").exists())
        info.assert_not_called()
        fs._backup.assert_not_called()

    def test_file_like_latest_match_aborts_without_claiming_older_job(self):
        for selected in ("", "job-9"):
            with self.subTest(selected=selected), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                plan, fs, incoming, pool = self.fixture(root, selected)
                leaf = pool / "job-9"
                leaf.write_bytes(b"not a folder")
                self.assert_rejected(root, plan, fs, incoming)
                self.assertEqual(leaf.read_bytes(), b"not a folder")

    def test_disappearing_pool_leaf_aborts_after_listing_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, fs, incoming, pool = self.fixture(root, "job-9")
            with mock.patch.object(fs, "list_directory", side_effect=[
                    ["job-9"], ["job-9"]]):
                self.assert_rejected(root, plan, fs, incoming)

    def test_link_or_dangling_link_aborts(self):
        for dangling in (False, True):
            with self.subTest(dangling=dangling), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                plan, fs, incoming, pool = self.fixture(root)
                target = root / "unrelated"
                if not dangling:
                    target.mkdir()
                    (target / "keep").write_bytes(b"unrelated")
                leaf = pool / "job-9"
                try:
                    leaf.symlink_to(target, target_is_directory=True)
                except (OSError, NotImplementedError):
                    self.skipTest("symlink creation unavailable")
                self.assert_rejected(root, plan, fs, incoming)
                self.assertTrue(leaf.is_symlink())
                if not dangling:
                    self.assertEqual((target / "keep").read_bytes(), b"unrelated")

    @unittest.skipUnless(os.name == "nt", "Windows junction fixture")
    def test_junction_aborts_before_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, fs, incoming, pool = self.fixture(root)
            target = root / "unrelated"
            target.mkdir()
            (target / "keep").write_bytes(b"unrelated")
            leaf = pool / "job-9"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(leaf), str(target)],
                capture_output=True, text=True, check=False)
            if result.returncode:
                self.skipTest("junction creation unavailable")
            try:
                self.assert_rejected(root, plan, fs, incoming)
                self.assertEqual((target / "keep").read_bytes(), b"unrelated")
            finally:
                leaf.rmdir()

    def test_real_selected_leaf_keeps_existing_acquisition_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan, fs, incoming, pool = self.fixture(root)
            (pool / "job-9").mkdir()
            self.assertEqual(WorkPoolManager(plan, fs).acquire(), "job-9")
            self.assertTrue((incoming / "job-1").is_dir())
            self.assertFalse((incoming / "job-9").exists())
            self.assertEqual((root / "AutoBertClassify_Processing" /
                              "job-9" / "keep").read_bytes(), b"incoming")


if __name__ == "__main__":
    unittest.main()
