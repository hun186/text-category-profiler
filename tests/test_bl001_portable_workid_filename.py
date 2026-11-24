"""Cross-platform external Work-ID child-name grammar excludes Win32 traps."""
import unittest
from unittest import mock

from text_category_profiler.pipeline.workpool import (
    DeliveryManager, WorkPoolManager, validate_external_work_id,
)
from tests.test_workpool_manager import RecordingFileSystem, plan


class PortableWorkIDFilenameTests(unittest.TestCase):
    def test_each_win32_reserved_character_is_rejected_anywhere(self):
        for illegal in '<>"|?*':
            for work_id in ("job" + illegal + "1", illegal + "start"):
                with self.subTest(name=repr(work_id)):
                    with self.assertRaisesRegex(
                            ValueError, "EXTERNAL_WORK_ID_INVALID"):
                        validate_external_work_id(work_id)

    def test_literal_ordinary_unicode_and_punctuation_still_valid(self):
        for work_id in ("中文_2026", "project (2)", "report+v1",
                        ".hidden", "work.001", "#T#類別"):
            with self.subTest(name=work_id):
                self.assertEqual(validate_external_work_id(work_id),
                                 work_id)

    def test_bad_preselected_id_has_zero_io(self):
        fs = RecordingFileSystem()
        with self.assertRaisesRegex(ValueError,
                                    "EXTERNAL_WORK_ID_INVALID"):
            WorkPoolManager(plan(work_id="job*wildcard"), fs).acquire()
        self.assertEqual(fs.calls, [])

    def test_bad_discovered_id_is_not_moved_or_backed_up(self):
        work_id = "job?unportable"
        fs = RecordingFileSystem({
            "/jobs/AutoBertClassify": [work_id],
            "/jobs/WorkPool": [work_id],
        })
        with self.assertRaisesRegex(ValueError,
                                    "EXTERNAL_WORK_ID_INVALID"):
            WorkPoolManager(plan(), fs).acquire()
        self.assertEqual([x[0] for x in fs.calls], ["list", "list"])

    def test_bad_delivery_id_prevents_all_side_effects(self):
        fs = RecordingFileSystem(system="Linux")
        log = mock.Mock()
        with self.assertRaisesRegex(ValueError,
                                    "EXTERNAL_WORK_ID_INVALID"):
            DeliveryManager(
                plan(work_id='job"quote', remove_dataset=True),
                fs, output_logger=log,
            ).backup_and_complete("/private")
        self.assertEqual(fs.calls, [])
        log.assert_not_called()


if __name__ == "__main__":
    unittest.main()
