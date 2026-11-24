"""BL-001 Windows DOS device names cannot be external WorkPool child IDs."""
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import (
    DeliveryManager,
    WorkPoolManager,
    is_windows_device_work_id,
    validate_external_work_id,
)
from tests.test_workpool_manager import RecordingFileSystem, plan


RESERVED = (
    "CON", "con", "CON.txt", "Con.EXTRA", "PRN", "prn.log",
    "AUX", "aux.foo", "NUL", "nul.json", "CONIN$", "CONOUT$",
    "COM1", "com9", "COM1.job", "LPT1", "lpt9.txt",
    "COM¹", "COM².ext", "COM³", "LPT¹", "LPT².job", "LPT³",
)

SAFE = (
    "CONNECTION", "CON-filename", "NUL1", "COM0", "COM10",
    "LPT0", "LPT10", "condata", "com1-job", "com1_data",
    "中文 CON 分類", ".hidden", "job.2026", "job 2026",
)


class WorkIDWindowsDeviceTests(unittest.TestCase):
    def test_rejects_reserved_device_names_and_extensions_independent_of_host(self):
        for value in RESERVED:
            with self.subTest(value=value):
                self.assertTrue(is_windows_device_work_id(value))
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    validate_external_work_id(value)

    def test_valid_single_children_are_not_overrestricted(self):
        for value in SAFE:
            with self.subTest(value=value):
                self.assertFalse(is_windows_device_work_id(value))
                self.assertEqual(validate_external_work_id(value), value)

    def test_invalid_preselected_id_refused_before_any_filesystem_call(self):
        for value in RESERVED:
            with self.subTest(value=value):
                fs = RecordingFileSystem({
                    "/jobs/AutoBertClassify": [value],
                    "/jobs/WorkPool": [value],
                })
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    WorkPoolManager(plan(work_id=value), fs).acquire()
                self.assertEqual(fs.calls, [])

    def test_invalid_discovered_id_fails_before_mkdir_and_move(self):
        for value in RESERVED:
            with self.subTest(value=value):
                fs = RecordingFileSystem({
                    "/jobs/AutoBertClassify": [value],
                    "/jobs/WorkPool": [value],
                })
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    WorkPoolManager(plan(), fs).acquire()
                self.assertEqual([call[0] for call in fs.calls], ["list", "list"])

    def test_invalid_delivery_fails_before_backup_chown_or_complete(self):
        for value in RESERVED:
            with self.subTest(value=value):
                fs = RecordingFileSystem(system="Linux")
                success = mock.Mock()
                with self.assertRaisesRegex(ValueError, "EXTERNAL_WORK_ID_INVALID"):
                    DeliveryManager(
                        plan(work_id=value, remove_dataset=True),
                        fs, output_logger=success,
                    ).backup_and_complete("/private-test-output")
                self.assertEqual(fs.calls, [])
                success.assert_not_called()

    def test_empty_id_remains_explicit_no_external_work_mode(self):
        self.assertFalse(is_windows_device_work_id(""))
        fs = RecordingFileSystem()
        DeliveryManager(plan(work_id=""), fs).backup_and_complete("/dataset")
        self.assertEqual(fs.calls, [])


if __name__ == "__main__":
    unittest.main()
