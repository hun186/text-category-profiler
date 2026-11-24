"""BL-001 guard against path-like external WorkIDs; no real WorkPool."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import (
    DeliveryManager, WorkPoolManager, validate_external_work_id,
)
from tests.test_workpool_manager import RecordingFileSystem, plan


INVALID_IDS = (
    ".", "..", "../escape", "..\\escape", "sub/job",
    "sub\\job", "/absolute", "\\absolute", "C:relative",
    "C:\\absolute", "\\\\server\\share\\job", "job:stream",
    "trailing.", "trailing ", "newline\njob", "tab\tjob",
    "null\x00job", "delete\x7fjob", "   ", None, 42,
    "job<evil", "job>evil", 'job"evil', "job|evil", "job?evil",
    "job*evil",
)


class ExternalWorkIDValidationTests(unittest.TestCase):
    def test_rejects_pathlike_and_ambiguous_names_on_any_host(self):
        for work_id in INVALID_IDS:
            with self.subTest(work_id=repr(work_id)):
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    validate_external_work_id(work_id)

    def test_valid_single_child_name_preserves_unicode_and_interior_spaces(self):
        for work_id in ("job-001", "#T#中文類別", "台灣 新聞 2026", "a.b", ".hidden", "job_7"):
            with self.subTest(work_id=work_id):
                self.assertEqual(validate_external_work_id(work_id), work_id)

    def test_invalid_preselected_id_fails_before_any_filesystem_operation(self):
        for work_id in INVALID_IDS:
            with self.subTest(work_id=repr(work_id)):
                fs = RecordingFileSystem({"/jobs/AutoBertClassify": ["job-a"],
                                          "/jobs/WorkPool": ["job-a"]})
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    WorkPoolManager(plan(work_id=work_id), fs).acquire()
                self.assertEqual(fs.calls, [])

    def test_invalid_discovered_id_fails_before_mkdir_move(self):
        for work_id in INVALID_IDS:
            with self.subTest(work_id=repr(work_id)):
                # Simulate a malformed remote listing; ordinary os.listdir
                # normally cannot return separators, but an injected adapter can.
                fs = RecordingFileSystem({
                    "/jobs/AutoBertClassify": [work_id],
                    "/jobs/WorkPool": [work_id],
                })
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    WorkPoolManager(plan(), fs).acquire()
                self.assertEqual([call[0] for call in fs.calls], ["list", "list"])

    def test_invalid_delivery_prevents_every_backup_chown_move_and_log(self):
        for work_id in INVALID_IDS:
            with self.subTest(work_id=repr(work_id)):
                fs = RecordingFileSystem(system="Linux")
                success = mock.Mock()
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    DeliveryManager(
                        plan(work_id=work_id, remove_dataset=True),
                        fs, output_logger=success,
                    ).backup_and_complete("/private-data")
                self.assertEqual(fs.calls, [])
                success.assert_not_called()

    def test_suspicious_id_cannot_escape_private_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pool = root / "WorkPool"
            pool.mkdir()
            sentinel = root / "outside.txt"
            sentinel.write_bytes(b"untouched")
            fs = RecordingFileSystem()
            with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                DeliveryManager(
                    plan(work_id="../outside.txt", pool_path=str(pool)),
                    fs,
                ).backup_and_complete(str(root / "dataset"))
            self.assertEqual(sentinel.read_bytes(), b"untouched")
            self.assertEqual(fs.calls, [])
            self.assertEqual(list(pool.iterdir()), [])

    def test_valid_unicode_work_id_selected_without_renaming(self):
        work_id = "中文 工作單 12"
        fs = RecordingFileSystem({
            "/jobs/AutoBertClassify": [work_id],
            "/jobs/WorkPool": [work_id],
        })
        self.assertEqual(WorkPoolManager(plan(), fs).acquire(), work_id)
        self.assertEqual(len([call for call in fs.calls if call[0] == "move"]), 1)
        self.assertTrue(any(work_id in str(value)
                            for call in fs.calls for value in call[1:]))

    def test_valid_id_keeps_delivery_backup_and_move_contract(self):
        fs = RecordingFileSystem()
        DeliveryManager(plan(work_id="正常單號-01"), fs).backup_and_complete("/dataset")
        self.assertEqual(len([call for call in fs.calls if call[0] == "backup"]), 1)
        self.assertEqual(len([call for call in fs.calls if call[0] == "move"]), 1)
        self.assertEqual(
            fs.calls[0][1]["DesDir"],
            os.path.join("/jobs/WorkPool", "正常單號-01"),
        )

    def test_empty_work_id_preserves_optional_external_mode(self):
        fs = RecordingFileSystem()
        DeliveryManager(plan(work_id=""), fs).backup_and_complete("/dataset")
        self.assertFalse([x for x in fs.calls if x[0] in ("backup", "move")])


if __name__ == "__main__":
    unittest.main()
