"""Guarded Stage 4 in-place retry of an interrupted GUI workspace.

No model/server/Tulip imports. The real filesystem test uses a private
temporary WorkPool, never a user or hosted production workspace.
"""
from argparse import Namespace
from pathlib import Path
import tempfile
import unittest

from BertScript import visualization_stage as stage


class InterruptedStage4Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "WorkPool"
        self.root.mkdir()
        self.name = (
            "dataset_20261109140948_PytorchMMBERT_pt8059"
            "_is_running_TestResultVis"
        )
        self.running = self.root / self.name
        self.running.mkdir()
        (self.running / "test_results_verification.sql3").write_bytes(
            b"this is a fixture filename only"
        )
        self.model = Path(self.tmp.name) / "output_model"
        self.model.mkdir()
        self.args = Namespace(
            resume_interrupted_stage4=True,
            confirm_stage4_stopped=True,
            BertDatasetSubDir=str(self.running),
            WorkPoolROOT=str(self.root),
            ExecutionTime="20261109140948",
            ModelType="PytorchMMBERT",
            TRVPort=8059,
            TRVWebHost=True,
            public=False,
            modelDir=str(self.model),
            WeiTechFormatSepWorkPool=False,
            WeiTechFormatInputPATH="",
            WeiTechFormatOutputPATH="",
        )

    def validate(self, **changes):
        state = vars(self.args).copy()
        state.update(changes)
        return stage.validate_interrupted_stage4_resume(
            Namespace(**state), port_free=lambda port: port == 8059,
        )

    def test_explicit_resume_validates_exact_workspace_without_any_writes(self):
        db = self.running / "test_results_verification.sql3"
        snapshot = (db.read_bytes(), db.stat().st_mtime_ns)
        self.assertEqual(self.validate(), str(self.running))
        self.assertEqual((db.read_bytes(), db.stat().st_mtime_ns), snapshot)
        self.assertTrue(self.running.is_dir())

    def test_requires_stopped_confirmation_and_explicit_workspace_and_model(self):
        for change, code in [
            ({"confirm_stage4_stopped": False}, "STAGE4_RESUME_CONFIRM_REQUIRED"),
            ({"BertDatasetSubDir": ""}, "STAGE4_RESUME_EXPLICIT_WORKSPACE_REQUIRED"),
            ({"modelDir": ""}, "STAGE4_RESUME_EXPLICIT_MODEL_REQUIRED"),
            ({"modelDir": str(self.model / "missing")}, "STAGE4_RESUME_MODEL_MISSING"),
            ({"BertDatasetSubDir": str(self.root / "missing")}, "STAGE4_RESUME_WORKSPACE_MISMATCH"),
            ({"ExecutionTime": "20261109140949"}, "STAGE4_RESUME_WORKSPACE_MISMATCH"),
            ({"ModelType": "PytorchXLM"}, "STAGE4_RESUME_WORKSPACE_MISMATCH"),
            ({"TRVPort": 8060}, "STAGE4_RESUME_WORKSPACE_MISMATCH"),
            ({"ExecutionTime": "../bad"}, "STAGE4_RESUME_IDENTITY_INVALID"),
        ]:
            with self.subTest(change=change), self.assertRaisesRegex(
                RuntimeError, code,
            ):
                self.validate(**change)
        self.assertTrue(self.running.is_dir())

    def test_rejects_parallel_ready_and_completed_siblings(self):
        base = str(self.running)[:-len(stage.RUNNING_SUFFIX)]
        for suffix, expected_code in [
            (stage.READY_SUFFIX, "STAGE4_RESUME_READY_CONFLICT"),
            (stage.NEXT_SUFFIX, "STAGE4_RESUME_COMPLETE_CONFLICT"),
        ]:
            other = Path(base + suffix)
            with self.subTest(suffix=suffix):
                other.mkdir()
                try:
                    with self.assertRaisesRegex(RuntimeError, expected_code):
                        self.validate()
                finally:
                    other.rmdir()
        self.assertTrue(self.running.is_dir())

    def test_rejects_missing_source_and_port_in_use(self):
        db = self.running / "test_results_verification.sql3"
        db.unlink()
        with self.assertRaisesRegex(RuntimeError, "STAGE4_RESUME_SOURCE_MISSING"):
            self.validate()
        db.write_bytes(b"restored")
        with self.assertRaisesRegex(RuntimeError, "STAGE4_RESUME_PORT_OCCUPIED"):
            stage.validate_interrupted_stage4_resume(
                self.args, port_free=lambda _port: False
            )

    def test_rejects_symbolic_link_even_inside_workpool(self):
        alias = self.root / "untrusted_alias"
        try:
            alias.symlink_to(self.running, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable in this runtime")
        try:
            with self.assertRaisesRegex(RuntimeError, "STAGE4_RESUME_WORKSPACE_MISMATCH"):
                self.validate(BertDatasetSubDir=str(alias))
        finally:
            alias.unlink()

    def test_resume_plan_skips_initial_claim_and_only_completes_after_validation(self):
        plan = stage.build_visualization_plan(
            self.args, str(self.running), str(self.model)
        )
        self.assertTrue(plan.resume_existing_running)
        self.assertEqual(plan.running_workspace, str(self.running))
        self.assertEqual(
            plan.ready_workspace,
            str(self.running)[:-len(stage.RUNNING_SUFFIX)] + stage.READY_SUFFIX,
        )
        calls = []

        def rename(src, dst):
            calls.append((src, dst))
            Path(src).rename(dst)

        def application(path):
            self.assertEqual(path, str(self.running))
            self.assertTrue(self.running.is_dir())
            calls.append(("application", path))

        expected = plan.completed_workspace
        result = stage.run_visualization_stage(
            plan, rename=rename, application=application,
            start_server=lambda _: self.fail("TRVWebHost false for test"),
            validate=lambda path: Path(path).is_dir(),
        ) if False else None
        # Hosted startup is injected; it does not start any real server.
        actual = stage.run_visualization_stage(
            plan, rename=rename, application=application,
            start_server=lambda _: calls.append(("server", "not launched")),
            validate=lambda path: Path(path).is_dir(),
        )
        self.assertEqual(actual, expected)
        self.assertEqual(calls[0], ("application", str(self.running)))
        self.assertEqual(calls[1], ("server", "not launched"))
        self.assertEqual(calls[2], (str(self.running), expected))
        self.assertFalse(self.running.exists())
        self.assertTrue(Path(expected).is_dir())

    def test_interrupted_resume_error_does_not_rename_or_relabel_workpool(self):
        plan = stage.build_visualization_plan(
            self.args, str(self.running), str(self.model),
        )
        invoked = []
        with self.assertRaisesRegex(ValueError, "injected stopped server"):
            stage.run_visualization_stage(
                plan,
                rename=lambda src, dst: invoked.append((src, dst)),
                application=lambda path: invoked.append(("application", path)),
                start_server=lambda _: (_ for _ in ()).throw(
                    ValueError("injected stopped server")
                ),
                validate=lambda _: True,
            )
        self.assertTrue(self.running.is_dir())
        self.assertFalse(invoked[1:])


if __name__ == "__main__":
    unittest.main()
