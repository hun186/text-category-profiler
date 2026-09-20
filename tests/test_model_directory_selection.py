import argparse
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from tests.test_tcf_cli_contract import load_tcf_utils


class ModelDirectorySelectionTests(unittest.TestCase):
    def setUp(self):
        self.module = load_tcf_utils()
        self.args = argparse.Namespace(
            ExecutionTime="20260919195120",
            ModelType="PytorchMMBERT",
            TRVPort=8050,
            train=False,
            WorkPoolROOT="WorkPool",
            WeiTechworkIDPath="",
            WeiTechworkID="",
            BertDatasetSubDir="/explicit/dataset",
            modelDir="",
        )
        self.logger = types.SimpleNamespace(logW=mock.Mock())

    def make_picker(self, root):
        return self.module.datasetDirOutputDirPickers(
            args=self.args,
            datasetDirsROOT=str(root),
            outputDirsROOT=str(root),
            MPLOGGER=self.logger,
        )

    @staticmethod
    def candidate(root, timestamp, checkpoint=None, model_file=None):
        output = root / f"output_{timestamp}_PytorchMMBERT"
        output.mkdir()
        if checkpoint is not None:
            checkpoint_dir = output / checkpoint
            checkpoint_dir.mkdir()
            if model_file is not None:
                (checkpoint_dir / model_file).write_bytes(b"weights")
        return output

    def test_newest_valid_candidate_is_selected_with_checkpoint_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = self.candidate(
                root, "20260919195120", "checkpoint-3", "model.safetensors"
            )
            self.candidate(root, "20260919194841", "checkpoint-2", "pytorch_model.bin")
            displays = []
            self.module.key_values = lambda title, items, **_: displays.append(
                (title, dict(items))
            )

            self.assertEqual(self.make_picker(root).Pick_outputDir(), str(selected))

            selected_display = dict(displays)[selected.name]
            self.assertEqual(selected_display["status"], "usable / SELECTED")
            self.assertEqual(selected_display["checkpoint"], "checkpoint-3")
            self.assertEqual(selected_display["model file"], "model.safetensors")

    def test_selected_newest_candidate_is_not_invalidated_by_older_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = self.candidate(
                root, "20260919195120", "checkpoint-3", "model.safetensors"
            )
            older = self.candidate(root, "20260919194841")
            original_inspector = self.module.inspect_pytorch_output_candidate

            def inspect(output_dir):
                if Path(output_dir) == older:
                    raise OSError("older candidate became unreadable")
                return original_inspector(output_dir)

            with mock.patch.object(
                self.module, "inspect_pytorch_output_candidate", side_effect=inspect
            ) as inspector:
                actual = self.make_picker(root).Pick_outputDir()

            self.assertEqual(actual, str(selected))
            inspector.assert_called_once_with(str(selected))

    def test_invalid_newest_is_rejected_and_older_binary_candidate_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rejected = self.candidate(root, "20260919195120")
            selected = self.candidate(
                root, "20260919194841", "checkpoint-9", "pytorch_model.bin"
            )
            displays = []
            self.module.key_values = lambda title, items, **_: displays.append(
                (title, dict(items))
            )

            self.assertEqual(self.make_picker(root).Pick_outputDir(), str(selected))

            diagnostic_by_name = dict(displays)
            self.assertEqual(diagnostic_by_name[rejected.name]["status"], "rejected")
            self.assertEqual(
                diagnostic_by_name[rejected.name]["reason"],
                "no checkpoint-* directory found",
            )
            self.assertEqual(diagnostic_by_name[selected.name]["model file"], "pytorch_model.bin")

    def test_checkpoint_without_supported_model_file_has_specific_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rejected = self.candidate(root, "20260919195120", "checkpoint-3")
            (rejected / "checkpoint-3" / "config.json").write_text("{}", encoding="utf-8")
            displays = []
            self.module.key_values = lambda title, items, **_: displays.append(
                (title, dict(items))
            )

            self.assertIsNone(self.make_picker(root).Pick_outputDir())

            diagnostic = dict(displays)[rejected.name]
            self.assertEqual(diagnostic["status"], "rejected")
            self.assertEqual(
                diagnostic["reason"],
                "checkpoint directories contain no supported model file",
            )

    def test_no_usable_candidate_preserves_retry_and_failure_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.candidate(root, "20260919195120")
            conformer = self.module.freeModelDirConformer(
                args=self.args,
                outputDirsROOT=str(root),
                datasetDirsROOT=str(root),
                RetryLimit=1,
                MPLOGGER=self.logger,
            )

            with mock.patch.object(self.module.time, "sleep") as sleep, self.assertRaises(Exception):
                conformer.proc()

            sleep.assert_called_once_with(10)
            retry_message = self.logger.logW.call_args_list[0].args[0]
            self.assertIn(
                "matching model directories were inspected but none contained a usable checkpoint",
                retry_message,
            )

    def test_no_matching_candidate_has_distinct_retry_message(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conformer = self.module.freeModelDirConformer(
                args=self.args,
                outputDirsROOT=str(root),
                datasetDirsROOT=str(root),
                RetryLimit=1,
                MPLOGGER=self.logger,
            )

            with mock.patch.object(self.module.time, "sleep"), self.assertRaises(Exception):
                conformer.proc()

            retry_message = self.logger.logW.call_args_list[0].args[0]
            self.assertIn(
                "no matching model directories were found for PytorchMMBERT",
                retry_message,
            )

    def test_tf15_candidate_summary_remains_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output_20260919195120_TF15Bert"
            output.mkdir()
            (output / "model.meta").write_bytes(b"model")
            self.args.ModelType = "TF15Bert"
            displays = []
            self.module.summarize_sequence = lambda values, limit: str(list(values))
            self.module.key_values = lambda title, items, **_: displays.append(
                (title, dict(items))
            )

            self.assertEqual(self.make_picker(root).Pick_outputDir(), str(output))

            summary = dict(displays)["Model directory candidates"]
            self.assertIn(output.name, summary["latest"])

    def test_explicit_model_override_remains_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            explicit = root / "operator-selected-model"
            self.args.modelDir = str(explicit)
            picker = self.make_picker(root)

            with mock.patch.object(picker, "Pick_outputDir") as automatic_picker:
                _dataset, selected = picker.proc()

            self.assertEqual(selected, str(explicit))
            automatic_picker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
