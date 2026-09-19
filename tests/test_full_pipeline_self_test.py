import argparse
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from text_category_profiler.diagnostics.full_pipeline import (
    SmokeConfig,
    SmokeResult,
    build_root_command,
    evaluate_isolated,
    evaluate_real,
    parse_classifier_device,
    run_self_test,
)
from text_category_profiler.diagnostics.device import report_classifier_device


class FullPipelineSelfTestTests(unittest.TestCase):
    def self_test_args(self, profile):
        return argparse.Namespace(
            self_test=profile, require_cuda=False, TRVPort=8059,
            ModelType="PytorchMMBERT", modelDir="", FixedTestPATH="",
            TopicTreeDir="", TopicTreeFiles="TopicTree.csv",
        )

    def assert_structured_setup_failure(self, invoke, runtime_root, boundary):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            returncode = invoke()
        self.assertNotEqual(returncode, 0)
        self.assertIn(f"[FAIL] {boundary}", output.getvalue())
        self.assertIn("FINAL: FAIL", output.getvalue())
        self.assertFalse(runtime_root.exists())

    def test_real_model_facade_failure_is_structured_and_cleans_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            fixed = root / "fixed"
            model.mkdir()
            fixed.mkdir()
            runtime = root / "runtime"
            config = SmokeConfig(root, fixed, None, None, model,
                                 fixed_test_dirs=(fixed,), intercept_classifier=False)
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.config_from_cli",
                return_value=config,
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline._runtime_root",
                return_value=runtime,
            ):
                self.assert_structured_setup_failure(
                    lambda: run_self_test(self.self_test_args("real"), root),
                    runtime, "Model facade",
                )

    def test_real_model_facade_link_runtime_error_is_structured_and_cleans_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            fixed = root / "fixed"
            (model / "checkpoint-1").mkdir(parents=True)
            fixed.mkdir()
            runtime = root / "runtime"
            config = SmokeConfig(root, fixed, None, None, model,
                                 fixed_test_dirs=(fixed,), intercept_classifier=False)
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.config_from_cli",
                return_value=config,
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline._runtime_root",
                return_value=runtime,
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.create_model_facade",
                side_effect=RuntimeError(
                    f"cannot link model checkpoint {model / 'checkpoint-1'}"
                ),
            ):
                self.assert_structured_setup_failure(
                    lambda: run_self_test(self.self_test_args("real"), root),
                    runtime, "Model facade",
                )

    def test_runtime_allocation_oserror_is_structured_for_both_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for profile in ("isolated", "real"):
                with self.subTest(profile=profile), mock.patch(
                    "text_category_profiler.diagnostics.full_pipeline._runtime_root",
                    side_effect=OSError("cannot allocate temporary runtime"),
                ), mock.patch(
                    "text_category_profiler.diagnostics.full_pipeline.config_from_cli",
                    return_value=SmokeConfig(
                        root, root, None, None, root,
                        fixed_test_dirs=(root,), intercept_classifier=False,
                    ),
                ):
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        returncode = run_self_test(self.self_test_args(profile), root)
                    self.assertNotEqual(returncode, 0)
                    self.assertIn("[FAIL] Runtime setup", output.getvalue())
                    self.assertIn("cannot allocate temporary runtime", output.getvalue())
                    self.assertIn("FINAL: FAIL", output.getvalue())

    def test_process_launch_failure_is_structured_and_cleans_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            model = root / "model"
            fixed = root / "fixed"
            (model / "checkpoint-1").mkdir(parents=True)
            fixed.mkdir()
            runtime = root / "runtime"
            config = SmokeConfig(root, fixed, None, None, model,
                                 fixed_test_dirs=(fixed,), intercept_classifier=False)
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.config_from_cli",
                return_value=config,
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline._runtime_root",
                return_value=runtime,
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.subprocess.Popen",
                side_effect=OSError("cannot execute child"),
            ):
                self.assert_structured_setup_failure(
                    lambda: run_self_test(self.self_test_args("real"), root),
                    runtime, "Process launch",
                )

    def test_isolated_setup_failure_is_structured_and_cleans_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "runtime"
            with mock.patch(
                "text_category_profiler.diagnostics.full_pipeline._runtime_root",
                return_value=runtime,
            ), mock.patch(
                "text_category_profiler.diagnostics.full_pipeline.create_intercepted_model_copy",
                side_effect=OSError("fixture copy denied"),
            ):
                self.assert_structured_setup_failure(
                    lambda: run_self_test(self.self_test_args("isolated"), root),
                    runtime, "Runtime setup",
                )

    def test_device_reporter_emits_cpu_and_cuda_evidence(self):
        cpu = mock.Mock()
        cpu.cuda.is_available.return_value = False
        lines = []
        self.assertEqual(report_classifier_device(cpu, lines.append), ("cpu", None))
        self.assertEqual(lines, [
            "TCF_CLASSIFIER_DEVICE device=cpu torch_cuda_available=False"
        ])
        cuda = mock.Mock()
        cuda.cuda.is_available.return_value = True
        cuda.cuda.get_device_name.return_value = "GPU-0"
        lines = []
        self.assertEqual(report_classifier_device(cuda, lines.append), ("cuda:0", "GPU-0"))
        self.assertEqual(lines[-1], "TCF_CLASSIFIER_GPU name=GPU-0")

    def result(self, root, **changes):
        values = dict(
            command=("python", "TCFMain.py"), returncode=0, stdout="", stderr="",
            runtime_root=root / "runtime", workpool_root=root / "workpool",
            workspaces=(), classifier_marker=None, timed_out=False,
        )
        values.update(changes)
        return SmokeResult(**values)

    def test_child_command_excludes_diagnostic_flags(self):
        root = Path("/repo")
        config = SmokeConfig(root, None, None, None, root / "model")
        command = build_root_command(config, root / "workpool")
        for flag in ("--self-test", "--doctor", "--require-cuda"):
            self.assertNotIn(flag, command)

    def test_explicit_classifier_device_parser_rejects_generic_cuda_noise(self):
        self.assertEqual(
            parse_classifier_device(
                "TCF_CLASSIFIER_DEVICE device=cuda:0 torch_cuda_available=True\n"
                "TCF_CLASSIFIER_GPU name=NVIDIA H100 PCIe\n"
            ),
            ("cuda:0", True, "NVIDIA H100 PCIe"),
        )
        self.assertEqual(
            parse_classifier_device(
                "TCF_CLASSIFIER_DEVICE device=cpu torch_cuda_available=False\n"
            ),
            ("cpu", False, None),
        )
        for noise in ("CUDA SETUP failed", "Defaulting to libbitsandbytes_cpu.so", ""):
            self.assertEqual(parse_classifier_device(noise), (None, None, None))

    def test_isolated_evaluator_reports_each_contract_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "job_rdy_for_Spike"
            workspace.mkdir()
            for filename in ("test.tsv", "test.sql3", "test_results.tsv",
                             "test_results_verification.sql3"):
                (workspace / filename).write_text("x", encoding="utf-8")
            marker = root / "marker"
            marker.write_text("one\n", encoding="utf-8")
            result = self.result(root, workspaces=(workspace,), classifier_marker=marker)
            checks = evaluate_isolated(
                result, source_rows=2, result_rows=2,
                source_unchanged=True, default_workpool_unchanged=True,
            )
            self.assertFalse(any(check.status == "FAIL" for check in checks))

            mutations = (
                dict(workspaces=()),
                dict(workspaces=(workspace, root / "other_rdy_for_Spike")),
                dict(workspaces=(workspace, root / "job_is_running_RunClassfier")),
                dict(classifier_marker=root / "missing"),
                dict(timed_out=True),
                dict(returncode=3),
            )
            for mutation in mutations:
                with self.subTest(mutation=mutation):
                    values = dict(workspaces=(workspace,), classifier_marker=marker)
                    values.update(mutation)
                    changed = self.result(root, **values)
                    self.assertTrue(any(c.status == "FAIL" for c in evaluate_isolated(
                        changed, source_rows=2, result_rows=2,
                        source_unchanged=True, default_workpool_unchanged=True)))
            self.assertTrue(any(c.status == "FAIL" for c in evaluate_isolated(
                result, source_rows=2, result_rows=1,
                source_unchanged=False, default_workpool_unchanged=False)))

    def test_real_cuda_requirement_uses_only_explicit_classifier_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            final = root / "job_rdy_for_Spike"
            final.mkdir()
            base = self.result(root, workspaces=(final,))
            common = dict(model_unchanged=True, fixed_tests_unchanged=True,
                          classifier_executed=True)
            cuda = SmokeResult(**{**base.__dict__, "stdout":
                "TCF_CLASSIFIER_DEVICE device=cuda:0 torch_cuda_available=True\n"
                "TCF_CLASSIFIER_GPU name=GPU-0"})
            self.assertFalse(any(c.status == "FAIL" for c in evaluate_real(
                cuda, require_cuda=True, **common)))
            for evidence in (
                "TCF_CLASSIFIER_DEVICE device=cpu torch_cuda_available=False",
                "TCF_CLASSIFIER_DEVICE device=cuda:0 torch_cuda_available=False",
                "CUDA SETUP GPU memory", "",
            ):
                candidate = SmokeResult(**{**base.__dict__, "stdout": evidence})
                self.assertTrue(any(c.status == "FAIL" for c in evaluate_real(
                    candidate, require_cuda=True, **common)))


if __name__ == "__main__":
    unittest.main()
