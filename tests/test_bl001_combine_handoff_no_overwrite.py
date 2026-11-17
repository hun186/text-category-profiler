"""Stage 3 success handoff safety, using only private temporary directories."""
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from tests.test_result_combination_stage import ResultCombinationStageTests
from tests.test_tcf_cli_contract import load_tcf_utils


class CombineHandoffSafetyTests(unittest.TestCase):
    def setUp(self):
        self.stage = ResultCombinationStageTests()._combine_module()
        helpers = load_tcf_utils()
        self.real_move = helpers._handoff_rename_noreplace
        self.stage._handoff_rename_noreplace = self.real_move
        self.stage._is_link_or_reparse = helpers._is_link_or_reparse
        self.stage.stage_done = mock.Mock()
        self.stage.key_values = mock.Mock()
        self.stage.MPlogger = mock.Mock()

    def folders(self, directory):
        src = Path(directory) / "dataset_case_is_running_CombineTestResult"
        dst = Path(directory) / "dataset_case_rdy_for_TestResultVis"
        src.mkdir()
        (src / "test.sql3").write_bytes(b"original-model-results")
        return src, dst

    def test_normal_success_has_exact_ready_state_and_no_source(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = self.folders(directory)
            self.stage._result_combination_handoff(str(src), str(dst))
            self.assertFalse(src.exists())
            self.assertEqual((dst / "test.sql3").read_bytes(),
                             b"original-model-results")
            self.stage.stage_done.assert_called_once_with("CombineTestResult")

    def test_existing_ready_folder_is_preserved_without_move(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = self.folders(directory)
            dst.mkdir()
            (dst / "owner.txt").write_bytes(b"do-not-replace")
            with self.assertRaisesRegex(
                FileExistsError, "COMBINE_HANDOFF_DESTINATION_ALREADY_EXISTS"
            ):
                self.stage._result_combination_handoff(str(src), str(dst))
            self.assertTrue(src.is_dir())
            self.assertEqual((dst / "owner.txt").read_bytes(), b"do-not-replace")
            self.stage.stage_done.assert_not_called()

    def test_destination_created_after_precheck_is_still_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = self.folders(directory)
            def competing_move(source, destination):
                dst.mkdir()
                (dst / "owned.txt").write_bytes(b"other-worker")
                return self.real_move(source, destination)
            self.stage._handoff_rename_noreplace = competing_move
            with self.assertRaises((FileExistsError, OSError)):
                self.stage._result_combination_handoff(str(src), str(dst))
            self.assertEqual((dst / "owned.txt").read_bytes(), b"other-worker")
            self.assertTrue(src.is_dir())
            self.assertFalse((dst / "test.sql3").exists())
            self.stage.stage_done.assert_not_called()

    def test_copy_fallback_partial_completion_preserves_both_sides(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = self.folders(directory)
            def partial_copy(source, destination):
                shutil.copytree(source, destination)
                # Simulate cross-device source-removal failure after copy.
            self.stage._handoff_rename_noreplace = partial_copy
            with self.assertRaisesRegex(RuntimeError, "COMBINE_HANDOFF_NOT_COMPLETE"):
                self.stage._result_combination_handoff(str(src), str(dst))
            self.assertEqual((src / "test.sql3").read_bytes(),
                             b"original-model-results")
            self.assertEqual((dst / "test.sql3").read_bytes(),
                             b"original-model-results")
            self.stage.stage_done.assert_not_called()

    def test_source_suffix_and_destination_mismatch_fail_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = self.folders(directory)
            with self.assertRaisesRegex(
                ValueError, "COMBINE_HANDOFF_DESTINATION_MISMATCH"
            ):
                self.stage._result_combination_handoff(
                    str(src), str(Path(directory) / "wrong-destination")
                )
            different = Path(directory) / "dataset_unexpected"
            different.mkdir()
            with self.assertRaisesRegex(
                ValueError, "COMBINE_HANDOFF_INVALID_SOURCE_STATE"
            ):
                self.stage._result_combination_handoff(str(different), str(dst))
            self.assertTrue(src.is_dir())
            self.assertFalse(dst.exists())
            self.stage.stage_done.assert_not_called()

    def test_symlinked_source_is_not_moved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real-model-output"
            real.mkdir()
            src = root / "dataset_case_is_running_CombineTestResult"
            dst = root / "dataset_case_rdy_for_TestResultVis"
            try:
                src.symlink_to(real, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privilege unavailable")
            with self.assertRaisesRegex(
                FileNotFoundError, "COMBINE_HANDOFF_SOURCE_NOT_A_DIRECTORY"
            ):
                self.stage._result_combination_handoff(str(src), str(dst))
            self.assertTrue(real.is_dir())
            self.assertFalse(dst.exists())

    def test_post_success_logger_error_does_not_repeat_move(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = self.folders(directory)
            calls = []
            def counted_move(source, destination):
                calls.append((source, destination))
                self.real_move(source, destination)
            self.stage._handoff_rename_noreplace = counted_move
            self.stage.MPlogger.return_value.logW.side_effect = OSError("log unavailable")
            self.stage._result_combination_handoff(str(src), str(dst))
            self.assertEqual(len(calls), 1)
            self.assertFalse(src.exists())
            self.assertTrue(dst.is_dir())
            self.stage.stage_done.assert_called_once_with("CombineTestResult")


if __name__ == "__main__":
    unittest.main()
