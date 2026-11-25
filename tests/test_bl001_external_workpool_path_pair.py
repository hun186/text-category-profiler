"""External WorkPool path pairs must not silently disable job acquisition."""
import unittest
from unittest import mock

from tests.test_tcf_main_characterization import default_args, load_main
from tests.test_workpool_manager import RecordingFileSystem, plan
from text_category_profiler.pipeline.workpool import (
    DeliveryManager, WorkPoolManager, validate_external_workpool_path_pair,
)


class ExternalWorkPoolPathPairTests(unittest.TestCase):
    def test_path_pair_is_all_or_none(self):
        for incoming, pool, expected in (
            ("", "", False), ("/incoming", "/pool", True),
        ):
            with self.subTest(pair=(incoming, pool)):
                self.assertIs(
                    validate_external_workpool_path_pair(incoming, pool),
                    expected,
                )
        for incoming, pool in (
            ("", "/pool"), ("/incoming", ""), (None, "/pool"),
            ("/incoming", None), (1, "/pool"), ("/incoming", object()),
        ):
            with self.subTest(pair=(incoming, pool)):
                with self.assertRaisesRegex(
                        ValueError, "EXTERNAL_WORKPOOL_PATH_PAIR_REQUIRED"):
                    validate_external_workpool_path_pair(incoming, pool)

    def test_root_data_convert_rejects_both_one_sided_configurations(self):
        for incoming, pool in (("/incoming", ""), ("", "/pool")):
            with self.subTest(pair=(incoming, pool)):
                args = default_args(
                    WeiTechworkIDPath=incoming,
                    WeiTechWorkPoolPATH=pool,
                )
                events = []
                module = load_main(args, trace=events)
                with self.assertRaisesRegex(
                        ValueError, "EXTERNAL_WORKPOOL_PATH_PAIR_REQUIRED"):
                    module.DataConvert(args, {"start": 0})
                self.assertEqual(
                    [x for x in events if x and x[0] == "command"], [],
                )

    def test_direct_manager_fails_without_listing_any_directory(self):
        for incoming, pool in (("/incoming", ""), ("", "/pool"), ("", "")):
            with self.subTest(pair=(incoming, pool)):
                fs = RecordingFileSystem()
                with self.assertRaisesRegex(
                        ValueError, "EXTERNAL_WORKPOOL_PATH_PAIR_REQUIRED"):
                    WorkPoolManager(plan(
                        incoming_path=incoming, pool_path=pool), fs).acquire()
                self.assertEqual(fs.calls, [])

    def test_delivery_nonempty_id_fails_before_any_backup(self):
        for incoming, pool in (("/incoming", ""), ("", "/pool"), ("", "")):
            with self.subTest(pair=(incoming, pool)):
                fs = RecordingFileSystem()
                log = mock.Mock()
                with self.assertRaisesRegex(
                        ValueError, "EXTERNAL_WORKPOOL_PATH_PAIR_REQUIRED"):
                    DeliveryManager(
                        plan(
                            incoming_path=incoming, pool_path=pool,
                            work_id="job-1", remove_dataset=True,
                        ), fs, output_logger=log,
                    ).backup_and_complete("/private-dataset")
                self.assertEqual(fs.calls, [])
                log.assert_not_called()

    def test_empty_work_id_generic_cleanup_retains_nonjob_semantics(self):
        fs = RecordingFileSystem()
        DeliveryManager(
            plan(incoming_path="/incoming", pool_path="",
                 work_id="", remove_dataset=True),
            fs,
        ).backup_and_complete("/dataset")
        self.assertEqual([x[0] for x in fs.calls], ["backup"])


if __name__ == "__main__":
    unittest.main()
