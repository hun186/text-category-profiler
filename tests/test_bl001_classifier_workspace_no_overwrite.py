"""Stage 2 classifier workspace collision tests; private temp dirs only."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from argparse import Namespace
from unittest import mock

from BertScript.classifier_stage import ClassifierPlan, run_classifier_stage
from tests.test_classifier_stage import ClassifierStageTests
from tests.test_tcf_cli_contract import load_tcf_utils


class ClassifierWorkspaceNoOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.entry = ClassifierStageTests()._runclassifier_module()
        helpers = load_tcf_utils()
        self.real_move = helpers._handoff_rename_noreplace
        for name, replacement in (
                ("_handoff_rename_noreplace", self.real_move),
                ("_is_link_or_reparse", helpers._is_link_or_reparse),
                ("stage_done", mock.Mock()),
                ("key_values", mock.Mock()),
                ("MPlogger", mock.Mock())):
            patcher = mock.patch.object(self.entry, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)

    def folders(self, parent):
        root = Path(parent)
        ready = root / "dataset_rdy_for_RunClassfier"
        running = root / "dataset_is_running_RunClassfier"
        complete = root / "dataset_rdy_for_CombineTestResult"
        ready.mkdir()
        (ready / "fixture.sql3").write_bytes(b"private-fixture")
        return ready, running, complete

    def plan(self, source):
        return ClassifierPlan(
            Namespace(train=False, test=True), str(source), str(Path(source).parent),
            "echo fake classifier", "pytorch",
        )

    def execute(self, plan, **changes):
        call_args = dict(
            rename=self.entry._classifier_transition_noreplace,
            handoff=self.entry._classifier_handoff,
            system=lambda _: 0, result_files=[],
            finalize=lambda _: None,
            warn=lambda _: self.fail("unexpected warning"),
        )
        call_args.update(changes)
        return run_classifier_stage(plan, **call_args)

    def test_real_production_adapters_complete_without_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            result = self.execute(self.plan(ready))
            self.assertEqual(result, str(complete))
            self.assertFalse(ready.exists())
            self.assertFalse(running.exists())
            self.assertEqual((complete / "fixture.sql3").read_bytes(), b"private-fixture")

    def test_valid_ready_path_with_trailing_separator_keeps_slash_style(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            outcome = self.execute(self.plan(str(ready) + os.sep))
            self.assertEqual(outcome, str(complete))
            self.assertTrue((complete / "fixture.sql3").is_file())
            self.assertFalse(ready.exists())

    def test_existing_running_ctrl_c_workspace_is_untouched(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            running.mkdir()
            (running / "ctrl-c-leftover").write_bytes(b"keep")
            system = mock.Mock()
            with self.assertRaisesRegex(
                    FileExistsError, "CLASSIFIER_DESTINATION_ALREADY_EXISTS"):
                self.execute(self.plan(ready), system=system)
            system.assert_not_called()
            self.assertEqual((running / "ctrl-c-leftover").read_bytes(), b"keep")
            self.assertTrue((ready / "fixture.sql3").is_file())
            self.assertFalse(complete.exists())

    def test_existing_combination_ready_folder_preserved_after_classifier(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            complete.mkdir()
            (complete / "other-owner").write_bytes(b"keep")
            with self.assertRaisesRegex(
                    FileExistsError, "CLASSIFIER_DESTINATION_ALREADY_EXISTS"):
                self.execute(self.plan(ready))
            self.assertFalse(ready.exists())
            self.assertTrue((running / "fixture.sql3").is_file())
            self.assertEqual((complete / "other-owner").read_bytes(), b"keep")
            self.entry.stage_done.assert_not_called()

    def test_competing_running_workspace_after_guard_does_not_get_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            def competitor(source, destination):
                running.mkdir()
                (running / "winner").write_bytes(b"keep")
                return self.real_move(source, destination)
            with mock.patch.object(self.entry, "_handoff_rename_noreplace", competitor):
                with self.assertRaises((FileExistsError, OSError)):
                    self.execute(self.plan(ready))
            self.assertTrue(ready.is_dir())
            self.assertEqual((running / "winner").read_bytes(), b"keep")
            self.assertFalse(complete.exists())

    def test_partial_copy_on_activation_aborts_before_classifier_command(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            command = mock.Mock()
            with mock.patch.object(
                self.entry, "_handoff_rename_noreplace",
                side_effect=lambda s, d: shutil.copytree(s, d),
            ):
                with self.assertRaisesRegex(
                        RuntimeError, "CLASSIFIER_WORKSPACE_TRANSITION_INCOMPLETE"):
                    self.execute(self.plan(ready), system=command)
            command.assert_not_called()
            self.assertTrue((ready / "fixture.sql3").is_file())
            self.assertTrue((running / "fixture.sql3").is_file())
            self.assertFalse(complete.exists())

    def test_partial_copy_on_completion_keeps_both_workspaces(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            def partial_final(source, destination):
                if str(destination).endswith("_rdy_for_CombineTestResult"):
                    shutil.copytree(source, destination)
                else:
                    self.real_move(source, destination)
            with mock.patch.object(
                    self.entry, "_handoff_rename_noreplace", partial_final,
            ):
                with self.assertRaisesRegex(
                        RuntimeError, "CLASSIFIER_WORKSPACE_TRANSITION_INCOMPLETE"):
                    self.execute(self.plan(ready))
            self.assertTrue((running / "fixture.sql3").is_file())
            self.assertTrue((complete / "fixture.sql3").is_file())
            self.entry.stage_done.assert_not_called()

    def test_invalid_workspace_transition_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            ready, running, complete = self.folders(root)
            with self.assertRaisesRegex(
                    ValueError, "CLASSIFIER_INVALID_WORKSPACE_TRANSITION"):
                self.entry._classifier_transition_noreplace(str(ready), str(complete))
            self.assertTrue(ready.exists())
            self.assertFalse(running.exists())

    def test_symlink_source_does_not_acquire_running_state(self):
        with tempfile.TemporaryDirectory() as root:
            actual = Path(root) / "real"
            actual.mkdir()
            source = Path(root) / "dataset_rdy_for_RunClassfier"
            try:
                source.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(
                    FileNotFoundError, "CLASSIFIER_SOURCE_NOT_A_DIRECTORY"):
                self.entry._classifier_transition_noreplace(
                    str(source), str(Path(root) / "dataset_is_running_RunClassfier")
                )
            self.assertTrue(source.is_symlink())
            self.assertTrue(actual.is_dir())

    @unittest.skipUnless(os.name == "nt", "Windows-specific junction check")
    def test_junction_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            actual = Path(root) / "real"
            actual.mkdir()
            source = Path(root) / "dataset_rdy_for_RunClassfier"
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(source), str(actual)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                self.skipTest("junction unavailable")
            try:
                with self.assertRaisesRegex(
                        FileNotFoundError, "CLASSIFIER_SOURCE_NOT_A_DIRECTORY"):
                    self.entry._classifier_transition_noreplace(
                        str(source),
                        str(Path(root) / "dataset_is_running_RunClassfier"),
                    )
            finally:
                source.rmdir()

    def test_production_entrypoint_injects_safe_activation_adapter(self):
        content = Path("BertScript/RunClassfier.py").read_text(encoding="utf-8")
        self.assertIn('"rename": _classifier_transition_noreplace', content)
        self.assertIn('    _classifier_transition_noreplace(source, destination)', content)


if __name__ == "__main__":
    unittest.main()
