"""Activation _rdy_for_CombineTestResult -> _is_running_ private-fixture safety."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from BertScript.result_combination_stage import (
    ResultCombinationPlan, activate_result_combination,
    run_result_combination_stage,
)
from tests.test_result_combination_stage import ResultCombinationStageTests
from tests.test_tcf_cli_contract import load_tcf_utils


class CombineActivationNoOverwriteTests(unittest.TestCase):
    def setUp(self):
        self.stage = ResultCombinationStageTests()._combine_module()
        helpers = load_tcf_utils()
        self.real_move = helpers._handoff_rename_noreplace
        self.stage._handoff_rename_noreplace = self.real_move
        self.stage._is_link_or_reparse = helpers._is_link_or_reparse

    def paths(self, temp):
        src = Path(temp) / "dataset_case_rdy_for_CombineTestResult"
        active = Path(temp) / "dataset_case_is_running_CombineTestResult"
        final = Path(temp) / "dataset_case_rdy_for_TestResultVis"
        src.mkdir()
        (src / "test.sql3").write_bytes(b"test-data-not-production")
        return src, active, final

    def plan(self, src):
        return ResultCombinationPlan(
            args=type("Args", (), {"datasetDataBaseSubDir": "datasetDB"})(),
            dataset_dir=str(src), output_dir=str(src.parent),
        )

    def test_successful_main_adapter_activation_and_final_handoff(self):
        with tempfile.TemporaryDirectory() as temp:
            src, active, final = self.paths(temp)
            trace = []
            def combine(running_plan, db_dir):
                trace.append("combine")
                self.assertEqual(running_plan.dataset_dir, str(active))
                self.assertTrue(active.is_dir())
                self.assertFalse(src.exists())
                self.assertEqual(db_dir, os.path.join(str(active), "datasetDB"))
            result = run_result_combination_stage(
                self.plan(src), combine=combine,
                activate_rename=self.stage._result_combination_activate,
                success_handoff=lambda source, dest: os.rename(source, dest),
            )
            self.assertEqual(trace, ["combine"])
            self.assertEqual(result, str(final))
            self.assertFalse(src.exists())
            self.assertFalse(active.exists())
            self.assertEqual((final / "test.sql3").read_bytes(),
                             b"test-data-not-production")

    def test_existing_running_destination_fails_before_computation(self):
        with tempfile.TemporaryDirectory() as temp:
            src, active, final = self.paths(temp)
            active.mkdir()
            (active / "existing-owner").write_bytes(b"must-survive")
            with self.assertRaisesRegex(
                FileExistsError, "COMBINE_ACTIVATION_DESTINATION_ALREADY_EXISTS"
            ):
                run_result_combination_stage(
                    self.plan(src),
                    combine=lambda *_: self.fail("must not compute"),
                    activate_rename=self.stage._result_combination_activate,
                    success_handoff=lambda *_: self.fail("must not handoff"),
                )
            self.assertEqual((src / "test.sql3").read_bytes(),
                             b"test-data-not-production")
            self.assertEqual((active / "existing-owner").read_bytes(), b"must-survive")
            self.assertFalse(final.exists())

    def test_competing_running_destination_created_after_guard_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            src, active, final = self.paths(temp)
            def concurrent_publisher(source, dest):
                active.mkdir()
                (active / "competing-worker").write_bytes(b"winner")
                return self.real_move(source, dest)
            self.stage._handoff_rename_noreplace = concurrent_publisher
            with self.assertRaises((FileExistsError, OSError)):
                self.stage._result_combination_activate(str(src), str(active))
            self.assertTrue(src.exists())
            self.assertEqual((active / "competing-worker").read_bytes(), b"winner")
            self.assertFalse(final.exists())

    def test_cross_device_partial_copy_cannot_start_combination(self):
        with tempfile.TemporaryDirectory() as temp:
            src, active, final = self.paths(temp)
            self.stage._handoff_rename_noreplace = lambda source, dest: (
                shutil.copytree(source, dest)
            )
            with self.assertRaisesRegex(RuntimeError, "COMBINE_ACTIVATION_NOT_COMPLETE"):
                run_result_combination_stage(
                    self.plan(src),
                    combine=lambda *_: self.fail("must not compute"),
                    activate_rename=self.stage._result_combination_activate,
                )
            self.assertEqual((src / "test.sql3").read_bytes(),
                             b"test-data-not-production")
            self.assertEqual((active / "test.sql3").read_bytes(),
                             b"test-data-not-production")
            self.assertFalse(final.exists())

    def test_nonterminal_state_name_rejected_without_renaming_parent(self):
        with tempfile.TemporaryDirectory() as temp:
            parent = Path(temp) / "parent_rdy_for_CombineTestResult"
            child = parent / "not_a_ready_workspace"
            child.mkdir(parents=True)
            with self.assertRaisesRegex(
                ValueError, "COMBINE_ACTIVATION_INVALID_READY_STATE"
            ):
                activate_result_combination(
                    self.plan(child),
                    rename=lambda *_: self.fail("must not rename"),
                )
            self.assertTrue(child.is_dir())

    def test_symlinked_ready_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "real-data"
            actual.mkdir()
            source = root / "dataset_case_rdy_for_CombineTestResult"
            try:
                source.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privilege unavailable")
            with self.assertRaisesRegex(
                FileNotFoundError, "COMBINE_ACTIVATION_SOURCE_NOT_A_DIRECTORY"
            ):
                self.stage._result_combination_activate(
                    str(source), str(root / "dataset_case_is_running_CombineTestResult")
                )
            self.assertTrue(actual.is_dir())
            self.assertTrue(source.is_symlink())

    @unittest.skipUnless(os.name == "nt", "Windows junction-specific check")
    def test_windows_junction_ready_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual"
            actual.mkdir()
            source = root / "dataset_case_rdy_for_CombineTestResult"
            proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(source),
                                   str(actual)], capture_output=True, text=True,
                                   check=False)
            if proc.returncode:
                self.skipTest("junction not available on this Windows host")
            try:
                with self.assertRaisesRegex(
                    FileNotFoundError, "COMBINE_ACTIVATION_SOURCE_NOT_A_DIRECTORY"
                ):
                    self.stage._result_combination_activate(
                        str(source),
                        str(root / "dataset_case_is_running_CombineTestResult")
                    )
                self.assertTrue(actual.is_dir())
            finally:
                source.rmdir()


if __name__ == "__main__":
    unittest.main()
