import argparse
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from text_category_profiler.diagnostics.checks import (
    check_cuda,
    check_fixed_test,
    check_model,
    check_topic_trees,
    discover_model_dir,
    run_doctor,
)
from text_category_profiler.pipeline.defaults import DEFAULT_MODEL_TYPE
from tests.test_tcf_cli_contract import load_tcf_utils


ClassfierOptionParser = load_tcf_utils().ClassfierOptionParser


class ProductionDiagnosticsTests(unittest.TestCase):
    def args(self, **overrides):
        values = vars(ClassfierOptionParser([])).copy()
        values.update(overrides)
        return argparse.Namespace(**values)

    def test_production_default_and_explicit_override(self):
        self.assertEqual(ClassfierOptionParser([]).ModelType, DEFAULT_MODEL_TYPE)
        self.assertEqual(DEFAULT_MODEL_TYPE, "PytorchMMBERT")
        self.assertEqual(
            ClassfierOptionParser(["-mdlType", "PytorchXLM"]).ModelType,
            "PytorchXLM",
        )

    def test_model_found_and_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model"
            checkpoint = model / "checkpoint-12"
            checkpoint.mkdir(parents=True)
            (checkpoint / "model.safetensors").write_bytes(b"weights")
            results = check_model(self.args(modelDir=str(model)), Path(directory))
            self.assertEqual([item.status for item in results], ["PASS", "PASS"])
            missing = check_model(
                self.args(modelDir=str(Path(directory) / "missing")), Path(directory)
            )
            self.assertIn("FAIL", [item.status for item in missing])

    def test_auto_model_resolver_failure_becomes_contextual_diagnostic(self):
        args = self.args(modelDir="", ModelType="PytorchMMBERT", TRVPort=8059)
        production_utils = types.ModuleType(
            "text_category_profiler.pipeline.TCF_utils"
        )
        production_utils.ClassfierOptionParser = mock.Mock(return_value=object())
        production_utils.datasetDirOutputDirPickers = mock.Mock(
            side_effect=TypeError(
                "expected str, bytes or os.PathLike object, not NoneType"
            )
        )
        with mock.patch.dict(sys.modules, {
            "text_category_profiler.pipeline.TCF_utils": production_utils,
        }):
            results = check_model(args, Path.cwd())
        self.assertEqual([result.status for result in results], ["FAIL"])
        details = "\n".join(results[0].details)
        self.assertIn("ModelType: PytorchMMBERT", details)
        self.assertIn("TRVPort: 8059", details)

    def test_auto_model_resolver_normalizes_picker_failure_and_restores_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            repository_root = Path(directory)
            original_cwd = Path.cwd()
            production_utils = types.ModuleType(
                "text_category_profiler.pipeline.TCF_utils"
            )
            production_utils.ClassfierOptionParser = mock.Mock(return_value=object())
            production_utils.datasetDirOutputDirPickers = mock.Mock(
                side_effect=TypeError(
                    "expected str, bytes or os.PathLike object, not NoneType"
                )
            )
            with mock.patch.dict(sys.modules, {
                "text_category_profiler.pipeline.TCF_utils": production_utils,
            }), self.assertRaisesRegex(
                RuntimeError, "PytorchMMBERT.*8059.*NoneType"
            ):
                discover_model_dir(repository_root, "PytorchMMBERT", 8059)
            self.assertEqual(Path.cwd(), original_cwd)

    def test_fixed_test_found_and_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            fixed = Path(directory) / "fixed"
            fixed.mkdir()
            found = check_fixed_test(self.args(FixedTestPATH=str(fixed)), Path(directory))
            missing = check_fixed_test(
                self.args(FixedTestPATH=str(Path(directory) / "missing")), Path(directory)
            )
            self.assertEqual(found.status, "PASS")
            self.assertEqual(missing.status, "FAIL")

    def test_topic_tree_found_and_missing_through_resolver(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tree = root / "TopicTree.csv"
            tree.write_text("root,child,2026\n", encoding="utf-8")
            resolver = mock.Mock(return_value=str(tree))
            found = check_topic_trees(
                self.args(TopicTreeFiles="TopicTree.csv"), root, resolver=resolver
            )
            self.assertEqual(found.status, "PASS")
            resolver.assert_called_once_with("TopicTree.csv", tree_source_dir="")
            missing = check_topic_trees(
                self.args(TopicTreeFiles="missing.csv"), root,
                resolver=mock.Mock(side_effect=FileNotFoundError("checked paths")),
            )
            self.assertEqual(missing.status, "FAIL")

    def test_cuda_available_and_unavailable(self):
        available = types.SimpleNamespace(
            __version__="2.7", cuda=types.SimpleNamespace(
                is_available=lambda: True, device_count=lambda: 2,
                get_device_name=lambda index: f"GPU-{index}",
            )
        )
        pytorch, cuda = check_cuda(torch_module=available)
        self.assertEqual((pytorch.status, cuda.status), ("PASS", "PASS"))
        self.assertIn("GPU-1", "\n".join(cuda.details))
        unavailable = types.SimpleNamespace(
            __version__="2.7+cpu", cuda=types.SimpleNamespace(
                is_available=lambda: False, device_count=lambda: 0,
                get_device_name=lambda index: "never",
            )
        )
        _pytorch, cuda = check_cuda(torch_module=unavailable)
        self.assertEqual(cuda.status, "WARN")
        _pytorch, required = check_cuda(torch_module=unavailable, require_cuda=True)
        self.assertEqual(required.status, "FAIL")

    def test_doctor_exit_codes_for_success_failure_and_warning_only(self):
        passing = types.SimpleNamespace(status="PASS", title="ok", details=("ok",))
        warning = types.SimpleNamespace(status="WARN", title="cuda", details=("no",))
        failing = types.SimpleNamespace(status="FAIL", title="missing", details=("no",))
        with mock.patch(
            "text_category_profiler.diagnostics.checks.collect_diagnostics",
            return_value=[passing, warning],
        ):
            self.assertEqual(run_doctor(self.args()), 0)
        with mock.patch(
            "text_category_profiler.diagnostics.checks.collect_diagnostics",
            return_value=[passing, failing],
        ):
            self.assertNotEqual(run_doctor(self.args()), 0)

    def test_help_exposes_doctor_default_and_test_set_meaning(self):
        output = io.StringIO()
        with self.assertRaises(SystemExit), contextlib.redirect_stdout(output):
            ClassfierOptionParser(["--help"])
        help_text = output.getvalue()
        self.assertIn("--doctor", help_text)
        self.assertIn("PytorchMMBERT", help_text)
        self.assertIn("Predict the test set", help_text)


if __name__ == "__main__":
    unittest.main()
