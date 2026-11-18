"""BL-001 Stage 4 safety checks: private directories only, no WorkPool or models."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from BertScript import visualization_stage as stage
from tests.test_tcf_cli_contract import load_tcf_utils


class VisualizationWorkspaceSafetyTests(unittest.TestCase):
    def setUp(self):
        # The production helper is reused, with optional data imports stubbed
        # solely within these tests. This never opens a real SQLite database.
        self.helpers = load_tcf_utils()
        self.original_move = self.helpers._handoff_rename_noreplace
        patcher = mock.patch.dict(
            sys.modules,
            {"text_category_profiler.pipeline.TCF_utils": self.helpers},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def workspace(self, parent):
        root = Path(parent)
        ready = root / "sample_rdy_for_TestResultVis"
        running = root / "sample_is_running_TestResultVis"
        complete = root / "sample_rdy_for_Spike"
        ready.mkdir()
        (ready / "private-result.sql3").write_bytes(b"private-not-production")
        return ready, running, complete

    @staticmethod
    def plan(ready):
        return stage.VisualizationPlan(
            ready_workspace=str(ready), output_dir=str(ready.parent),
            hosted=False, host="127.0.0.1", port=8059,
            weitech_separate_work_pool=False, weitech_input_path="",
            weitech_output_path="", ssl_context=None,
        )

    def test_real_production_default_protects_both_transitions(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            calls = []
            outcome = stage.run_visualization_stage(
                self.plan(ready),
                application=lambda p: calls.append((p, running.is_dir())),
                start_server=lambda _: self.fail("hosted disabled"),
                validate=lambda p: Path(p).is_dir(),
            )
            self.assertEqual(outcome, str(complete))
            self.assertEqual(calls, [(str(running), True)])
            self.assertFalse(ready.exists())
            self.assertFalse(running.exists())
            self.assertEqual(
                (complete / "private-result.sql3").read_bytes(),
                b"private-not-production",
            )

    def test_preexisting_running_workspace_stays_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            running.mkdir()
            (running / "ctrl-c-leftover").write_bytes(b"keep")
            with self.assertRaisesRegex(
                    FileExistsError, "VISUALIZATION_DESTINATION_ALREADY_EXISTS"):
                stage.run_visualization_stage(
                    self.plan(ready),
                    application=lambda *_: self.fail("must not start application"),
                    start_server=lambda *_: self.fail("must not host"),
                    validate=lambda *_: self.fail("must not validate"),
                )
            self.assertEqual((running / "ctrl-c-leftover").read_bytes(), b"keep")
            self.assertTrue((ready / "private-result.sql3").is_file())
            self.assertFalse(complete.exists())

    def test_preexisting_completed_workspace_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            complete.mkdir()
            (complete / "older-result").write_bytes(b"keep")
            seen = []
            def application(path):
                seen.append(path)
            with self.assertRaisesRegex(
                    FileExistsError, "VISUALIZATION_DESTINATION_ALREADY_EXISTS"):
                stage.run_visualization_stage(
                    self.plan(ready), application=application,
                    start_server=lambda *_: self.fail("must not host"),
                    validate=lambda _: True,
                )
            self.assertEqual(seen, [str(running)])
            self.assertTrue(running.is_dir())
            self.assertFalse(ready.exists())
            self.assertEqual((complete / "older-result").read_bytes(), b"keep")

    def test_competing_destination_created_after_exists_guard_is_preserved(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            def racing_move(source, destination):
                running.mkdir()
                (running / "other-worker").write_bytes(b"winner")
                return self.original_move(source, destination)
            self.helpers._handoff_rename_noreplace = racing_move
            with self.assertRaises((FileExistsError, OSError)):
                stage.run_visualization_stage(
                    self.plan(ready),
                    application=lambda *_: self.fail("application cannot run"),
                    start_server=lambda *_: self.fail("must not host"),
                    validate=lambda _: True,
                )
            self.assertEqual((running / "other-worker").read_bytes(), b"winner")
            self.assertTrue(ready.is_dir())
            self.assertFalse(complete.exists())

    def test_partial_copy_on_acquisition_aborts_and_preserves_both(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            self.helpers._handoff_rename_noreplace = (
                lambda src, dst: shutil.copytree(src, dst)
            )
            with self.assertRaisesRegex(
                    RuntimeError, "VISUALIZATION_STAGE_MOVE_INCOMPLETE"):
                stage.run_visualization_stage(
                    self.plan(ready),
                    application=lambda *_: self.fail("application cannot run"),
                    start_server=lambda *_: self.fail("must not host"),
                    validate=lambda _: True,
                )
            self.assertTrue((ready / "private-result.sql3").is_file())
            self.assertTrue((running / "private-result.sql3").is_file())
            self.assertFalse(complete.exists())

    def test_partial_copy_on_completion_keeps_running_and_ready(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            def conditional_move(src, dst):
                if str(dst).endswith(stage.NEXT_SUFFIX):
                    return shutil.copytree(src, dst)
                return self.original_move(src, dst)
            self.helpers._handoff_rename_noreplace = conditional_move
            with self.assertRaisesRegex(
                    RuntimeError, "VISUALIZATION_STAGE_MOVE_INCOMPLETE"):
                stage.run_visualization_stage(
                    self.plan(ready), application=lambda *_: None,
                    start_server=lambda *_: self.fail("must not host"),
                    validate=lambda _: True,
                )
            self.assertFalse(ready.exists())
            self.assertTrue((running / "private-result.sql3").is_file())
            self.assertTrue((complete / "private-result.sql3").is_file())

    def test_invalid_source_state_and_destination_fail_without_move(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.workspace(root)
            with self.assertRaisesRegex(
                    ValueError, "VISUALIZATION_INVALID_STAGE_TRANSITION"):
                stage._stage4_move_noreplace(str(ready), str(complete))
            wrong = Path(root) / "sample_unexpected"
            wrong.mkdir()
            with self.assertRaisesRegex(
                    ValueError, "VISUALIZATION_INVALID_STAGE_TRANSITION"):
                stage._stage4_move_noreplace(str(wrong), str(running))
            self.assertTrue(ready.is_dir())
            self.assertFalse(running.exists())

    def test_symlink_source_is_not_activated(self):
        with tempfile.TemporaryDirectory() as root:
            actual = Path(root) / "real-files"
            actual.mkdir()
            source = Path(root) / "sample_rdy_for_TestResultVis"
            try:
                source.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(
                    FileNotFoundError, "VISUALIZATION_SOURCE_NOT_A_DIRECTORY"):
                stage._stage4_move_noreplace(
                    str(source), str(Path(root) / "sample_is_running_TestResultVis")
                )
            self.assertTrue(source.is_symlink())
            self.assertTrue(actual.is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows-only junction fixture")
    def test_windows_junction_source_is_not_activated(self):
        with tempfile.TemporaryDirectory() as root:
            actual = Path(root) / "actual"
            actual.mkdir()
            source = Path(root) / "sample_rdy_for_TestResultVis"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source), str(actual)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("junction creation unavailable")
            try:
                with self.assertRaisesRegex(
                        FileNotFoundError, "VISUALIZATION_SOURCE_NOT_A_DIRECTORY"):
                    stage._stage4_move_noreplace(
                        str(source),
                        str(Path(root) / "sample_is_running_TestResultVis"),
                    )
                self.assertTrue(actual.is_dir())
            finally:
                source.rmdir()


if __name__ == "__main__":
    unittest.main()
