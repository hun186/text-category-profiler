"""BL-001 Stage 1 running directory acquisition; private fixtures only."""
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

from DatasetConverter import stage
from DatasetConverter.config import default_converter_settings
from DatasetConverter.core.stage_utils import acquire_stage_directory_exclusive
from tests.test_data_converter_stage_plan import converter_args


class StageOneExclusiveWorkspaceTests(unittest.TestCase):
    def plan(self, base):
        args = converter_args(WeiTechFormatInputPATH="", FixedTestPATH="fixture")
        with (
            mock.patch.object(stage, "parse_converter_options", return_value=args),
            mock.patch.object(stage, "pick_dataset_directories",
                              return_value=(str(base), "unused")),
        ):
            return stage.normalize_stage_plan(default_converter_settings(), argv=[])

    def activate(self, plan, work_root):
        fake_logger = mock.Mock()
        with (
            mock.patch.object(stage, "WORK_POOL_ROOT", str(work_root)),
            mock.patch.object(stage, "create_logger", return_value=fake_logger) as factory,
            mock.patch.object(stage, "stage_banner") as banner,
            mock.patch.object(stage, "key_values"),
        ):
            outcome = stage.activate_stage_context(plan)
        return outcome, factory, banner, fake_logger

    def test_new_workspace_acquired_before_logger(self):
        with tempfile.TemporaryDirectory() as root:
            pool = Path(root) / "WorkPool"
            plan = self.plan(pool / "dataset_case")
            outcome, factory, banner, log = self.activate(plan, pool)
            self.assertEqual(outcome.output_config.dataset_directory, plan.work_directory)
            self.assertTrue(Path(plan.work_directory).is_dir())
            factory.assert_any_call(logSubDir=f"{plan.work_directory}/logs")
            log.logW.assert_called_once()
            banner.assert_called_once()

    def test_preexisting_ctrl_c_folder_is_preserved_before_logging(self):
        with tempfile.TemporaryDirectory() as root:
            pool = Path(root) / "WorkPool"
            plan = self.plan(pool / "dataset_case")
            active = Path(plan.work_directory)
            active.mkdir(parents=True)
            (active / "unfinished.sql3").write_bytes(b"never-reuse")
            with (
                mock.patch.object(stage, "WORK_POOL_ROOT", str(pool)),
                mock.patch.object(stage, "create_logger") as factory,
                mock.patch.object(stage, "stage_banner") as banner,
                self.assertRaisesRegex(
                    FileExistsError, "DATACONVERTER_WORKSPACE_ALREADY_EXISTS"
                ),
            ):
                stage.activate_stage_context(plan)
            self.assertEqual((active / "unfinished.sql3").read_bytes(), b"never-reuse")
            factory.assert_not_called()
            banner.assert_not_called()

    def test_existing_empty_directory_or_file_refused(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            directory = root / "data_is_running_DataConverter"
            directory.mkdir()
            with self.assertRaises(FileExistsError):
                acquire_stage_directory_exclusive(str(directory))
            self.assertTrue(directory.is_dir())
            file = root / "file_is_running_DataConverter"
            file.write_bytes(b"keep")
            with self.assertRaises(FileExistsError):
                acquire_stage_directory_exclusive(str(file))
            self.assertEqual(file.read_bytes(), b"keep")

    def test_simultaneous_acquisition_has_exactly_one_winner(self):
        with tempfile.TemporaryDirectory() as root:
            target = str(Path(root) / "dataset_is_running_DataConverter")
            gate = threading.Barrier(2)
            def worker(_):
                gate.wait(timeout=10)
                try:
                    acquire_stage_directory_exclusive(target)
                except FileExistsError:
                    return "collision"
                return "created"
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(worker, range(2)))
            self.assertEqual(sorted(results), ["collision", "created"])
            self.assertTrue(Path(target).is_dir())

    def test_rejects_invalid_state_before_touching_disk(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("unexpected", "task_rdy_for_DataConverter",
                         "not_is_running_DataConverter_oversuffixed"):
                bad = str(Path(root) / name)
                with self.assertRaisesRegex(
                    ValueError, "DATACONVERTER_INVALID_WORKSPACE_PATH"
                ):
                    acquire_stage_directory_exclusive(bad)
                self.assertFalse(Path(bad).exists())
            with self.assertRaises(ValueError):
                acquire_stage_directory_exclusive(123)

    def test_symlink_and_broken_symlink_cannot_be_reused(self):
        with tempfile.TemporaryDirectory() as root:
            actual = Path(root) / "real"
            actual.mkdir()
            link = Path(root) / "run_is_running_DataConverter"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaises(FileExistsError):
                acquire_stage_directory_exclusive(str(link))
            self.assertTrue(link.is_symlink())
            self.assertTrue(actual.is_dir())
            dangling = Path(root) / "missing_is_running_DataConverter"
            dangling.symlink_to(Path(root) / "missing-target", target_is_directory=True)
            with self.assertRaises(FileExistsError):
                acquire_stage_directory_exclusive(str(dangling))
            self.assertTrue(dangling.is_symlink())

    @unittest.skipUnless(os.name == "nt", "Windows junction fixture")
    def test_windows_junction_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            actual = Path(root) / "real"
            actual.mkdir()
            link = Path(root) / "run_is_running_DataConverter"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(actual)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("junction creation unavailable")
            try:
                with self.assertRaises(FileExistsError):
                    acquire_stage_directory_exclusive(str(link))
                self.assertTrue(actual.is_dir())
            finally:
                link.rmdir()

    def test_logger_failure_does_not_cleanup_acquired_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            pool = Path(root) / "WorkPool"
            plan = self.plan(pool / "dataset_case")
            with (
                mock.patch.object(stage, "WORK_POOL_ROOT", str(pool)),
                mock.patch.object(stage, "stage_banner"),
                mock.patch.object(stage, "create_logger",
                                  side_effect=RuntimeError("logger unavailable")),
                self.assertRaisesRegex(RuntimeError, "logger unavailable"),
            ):
                stage.activate_stage_context(plan)
            self.assertTrue(Path(plan.work_directory).is_dir())


if __name__ == "__main__":
    unittest.main()
