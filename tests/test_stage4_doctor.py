"""Read-only Stage 4 doctor contracts, no GUI/model/server installations."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from BertScript import stage4_doctor as doctor


ROOT = Path(__file__).resolve().parents[1]
GOOD = {
    "dash": "3.4.0", "visdcc": "0.0.63", "comm": "0.2.3",
    "jaal": "0.1.5", "jaal-topology-viewer": "0.1.0",
    "dash-bootstrap-components": "0.13.1", "tulip-python": "6.0.0",
}


def checks(**overrides):
    values = dict(mode="full", versions=GOOD, has_topology=True,
                  has_tulip=True, python_version=(3, 11),
                  windows=True, path=r"C:\Windows\System32;D:\Anaconda\Library\bin",
                  workspace_names=[
                      "dataset_20261108120000_PytorchMMBERT_pt8059_rdy_for_TestResultVis",
                      "dataset_20261107120000_PytorchXLM_pt8059_rdy_for_Spike",
                  ])
    values.update(overrides)
    return doctor.collect_checks(**values)


class Stage4DoctorTests(unittest.TestCase):
    def test_full_mode_reports_ready_dataset_and_safe_python_dependencies(self):
        result = checks()
        self.assertFalse([x for x in result if x.status == "FAIL"], result)
        self.assertTrue(any(
            x.name == "WorkPool" and "matching PytorchMMBERT ready" in x.detail
            for x in result
        ))
        self.assertTrue(any(
            x.name == "Tulip DLL PATH" and x.status == "PASS"
            for x in result
        ))

    def test_independent_failing_import_and_path_checks_report_all_at_once(self):
        versions = dict(GOOD, dash="3.4.0", visdcc="0.0.50", comm="0.1.0")
        result = checks(versions=versions, path=r"C:\Windows;.",
                        has_topology=False, has_tulip=False,
                        workspace_names=[])
        failures = {x.name: x.detail for x in result if x.status == "FAIL"}
        self.assertIn("Dash/comm", failures)
        self.assertIn("Dash/visdcc", failures)
        self.assertIn("jaal_topology", failures)
        self.assertIn("Tulip DLL PATH", failures)
        self.assertIn("Tulip module", failures)
        self.assertIn("WorkPool", failures)
        self.assertIn("visdcc==0.0.63", failures["Dash/visdcc"])
        self.assertIn('set "PATH=%PATH:;.=%"', failures["Tulip DLL PATH"])
        self.assertIn("--viewer-only", failures["WorkPool"])

    def test_viewer_mode_never_inspects_workpool_or_tulip(self):
        with (
            mock.patch.object(doctor, "_workspaces",
                              side_effect=AssertionError("viewer must not read WorkPool")),
            mock.patch.object(doctor, "_module_available",
                              side_effect=AssertionError("no package probing")),
        ):
            result = checks(mode="viewer", path=".;relative", windows=True)
        self.assertFalse([x for x in result if x.status == "FAIL"], result)
        self.assertNotIn("WorkPool", {x.name for x in result})
        self.assertNotIn("Tulip DLL PATH", {x.name for x in result})

    def test_history_mode_only_checks_completed_or_interrupted_names(self):
        names = ["dataset_20261108120000_PytorchXLM_pt8059_rdy_for_Spike",
                 "dataset_20261107120000_PytorchXLM_pt8059_is_running_TestResultVis"]
        result = checks(mode="history", workspace_names=names)
        history = next(x for x in result if x.name == "WorkPool")
        self.assertEqual(history.status, "PASS")
        self.assertIn("completed=1", history.detail)
        self.assertIn("running/interrupted=1", history.detail)

    def test_missing_workpool_does_not_create_or_rename_paths(self):
        with tempfile.TemporaryDirectory() as root:
            workpool = Path(root) / "does_not_exist"
            with (
                mock.patch("os.rename", side_effect=AssertionError("rename")),
                mock.patch("os.replace", side_effect=AssertionError("replace")),
            ):
                result = checks(workspace_names=None, workpool=str(workpool))
            self.assertFalse(workpool.exists())
        self.assertEqual(next(x.status for x in result
                              if x.name == "WorkPool"), "FAIL")

    def test_completed_dataset_is_not_relabelled_as_ready_for_full_mode(self):
        result = checks(workspace_names=[
            "dataset_20261108120000_PytorchMMBERT_pt8059_rdy_for_Spike",
        ])
        message = next(x.detail for x in result if x.name == "WorkPool")
        self.assertIn("completed=1", message)
        self.assertIn("Do NOT rename", message)
        self.assertEqual(next(x.status for x in result if x.name == "WorkPool"),
                         "FAIL")

    def test_doctor_main_exits_nonzero_without_running_jaal_when_blocked(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.main(["--doctor", "--mode", "viewer", "--probe-jaal"],
                               inspector=lambda **_: [
                                   doctor.Check("FAIL", "visdcc", "Not installed")
                               ],
                               jaal_diagnose=mock.Mock(side_effect=AssertionError(
                                   "do not build Jaal after failure")))
        self.assertEqual(code, 2)
        self.assertIn("STAGE4_DOCTOR_FAIL", out.getvalue())
        self.assertIn("[SKIP] Jaal construction", out.getvalue())

    def test_doctor_main_can_invoke_optional_readonly_jaal_probe(self):
        out = io.StringIO()
        probe = mock.Mock(return_value=0)
        with contextlib.redirect_stdout(out):
            code = doctor.main(["--doctor", "--mode", "viewer", "--probe-jaal",
                                "--root", "TW Affairs"],
                               inspector=lambda **_: [
                                   doctor.Check("PASS", "Python", "3.11")
                               ],
                               jaal_diagnose=probe)
        self.assertEqual(code, 0)
        probe.assert_called_once_with("TW Affairs")
        self.assertIn("STAGE4_DOCTOR_PASS", out.getvalue())

    def test_direct_script_doctor_help_exits_before_heavy_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            run = subprocess.run(
                [sys.executable, str(ROOT / "BertScript/Test_result_Vis.py"),
                 "--doctor", "--help"],
                cwd=directory, text=True, capture_output=True,
                timeout=20, check=False,
            )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("--mode", run.stdout)
        self.assertIn("--probe-jaal", run.stdout)
        self.assertNotIn("WorkPool", run.stderr)

    def test_windows_launcher_forwards_options_without_installing_packages(self):
        bat = (ROOT / "run-stage4-doctor.bat").read_text(encoding="utf-8")
        self.assertIn("--doctor %*", bat)
        self.assertIn("exit /b %RC%", bat)
        self.assertNotIn("pip install", bat)


if __name__ == "__main__":
    unittest.main()
