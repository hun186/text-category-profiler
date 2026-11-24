"""BL-001 Stage 1 trailing path separator and exclusive acquisition regression."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from DatasetConverter import stage
from DatasetConverter.config import ConfigValidationError, default_converter_settings
from tests.test_data_converter_stage_plan import converter_args


class StageOneTrailingSeparatorTests(unittest.TestCase):
    def plan_for(self, picked):
        args = converter_args(test=False, FixedTestPATH="",
                              WeiTechFormatInputPATH="", TRVPort=8059)
        with (
            mock.patch.object(stage, "parse_converter_options", return_value=args),
            mock.patch.object(stage, "pick_dataset_directories",
                              return_value=(picked, "unused-output")),
        ):
            return stage.normalize_stage_plan(
                default_converter_settings(), argv=[]
            )

    def test_trailing_linux_separator_is_removed_before_suffix(self):
        with tempfile.TemporaryDirectory() as temp:
            base = str(Path(temp) / "job")
            expected = base + "_is_running_DataConverter"
            for picked in (base, base + "/", base + "///"):
                with self.subTest(picked=picked):
                    plan = self.plan_for(picked)
                    self.assertEqual(plan.work_directory, expected)
                    self.assertEqual(plan.args.BertDatasetSubDir, expected)
                    self.assertEqual(plan.output_config.dataset_directory, expected)

    def test_windows_path_keeps_internal_spelling_and_state_suffix(self):
        cases = (
            ("C:\\WorkPool\\job\\", "C:\\WorkPool\\job_is_running_DataConverter"),
            ("C:/WorkPool/job///", "C:/WorkPool/job_is_running_DataConverter"),
            ("\\\\server\\share\\job\\",
             "\\\\server\\share\\job_is_running_DataConverter"),
            ("relative\\folder\\\\", "relative\\folder_is_running_DataConverter"),
            ("relative/dir\\\\/", "relative/dir_is_running_DataConverter"),
        )
        for picked, expected in cases:
            with self.subTest(picked=picked):
                self.assertEqual(self.plan_for(picked).work_directory, expected)

    def test_invalid_root_and_ambiguous_bases_fail_before_activation(self):
        cases = ("", "/", "\\", "////", "C:\\", "C:/", "C:", "\\\\server\\share\\",
                 "\\\\server\\share", "//server/share/", ".", "./", "..", "../",
                 None, 123)
        for picked in cases:
            with self.subTest(picked=repr(picked)):
                with self.assertRaisesRegex(
                    ConfigValidationError, "DATACONVERTER_INVALID_DATASET_BASE_PATH"
                ):
                    self.plan_for(picked)

    def test_private_activation_creates_sibling_running_directory_only(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "job"
            plan = self.plan_for(str(base) + os.sep)
            expected = Path(str(base) + "_is_running_DataConverter")
            self.assertEqual(Path(plan.work_directory), expected)
            fake_logger = mock.Mock()
            with (
                mock.patch.object(stage, "WORK_POOL_ROOT", str(Path(temp) / "Pool")),
                mock.patch.object(stage, "create_logger", return_value=fake_logger),
                mock.patch.object(stage, "stage_banner"),
                mock.patch.object(stage, "info"),
            ):
                context = stage.activate_stage_context(plan)
            self.assertEqual(context.output_config.dataset_directory, str(expected))
            self.assertTrue(expected.is_dir())
            self.assertFalse(base.exists())
            self.assertFalse((base / "_is_running_DataConverter").exists())

    def test_preexisting_sibling_running_directory_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp) / "job"
            plan = self.plan_for(str(base) + "/")
            running = Path(plan.work_directory)
            running.mkdir()
            (running / "ctrl-c-leftover.txt").write_bytes(b"keep")
            logger = mock.Mock()
            with (
                mock.patch.object(stage, "WORK_POOL_ROOT", str(Path(temp) / "Pool")),
                mock.patch.object(stage, "create_logger", logger),
                mock.patch.object(stage, "stage_banner"),
                self.assertRaisesRegex(
                    FileExistsError, "DATACONVERTER_WORKSPACE_ALREADY_EXISTS"
                ),
            ):
                stage.activate_stage_context(plan)
            logger.assert_not_called()
            self.assertEqual((running / "ctrl-c-leftover.txt").read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
