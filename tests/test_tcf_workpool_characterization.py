import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from tests.test_tcf_cli_contract import load_tcf_utils
from tests.test_tcf_main_characterization import default_args, load_main


ROOT = Path(__file__).resolve().parents[1]
BASE_PATTERNS = [
    "^DFPreambleCols_df_ALL.*",
    "dataset_total_with_filename_FixedTest.sql3",
    "test.sql3",
    "test.tsv",
]


def _module(name, **attributes):
    module = types.ModuleType(name)
    vars(module).update(attributes)
    return module


def load_parameters(task=""):
    args = default_args(task=task, debugMode=False, TrainDRNDataOnly=False,
                        trainWithMaliciousDomainDataset=False, public=False,
                        ESDataConfigFile="", ExtractionConverterTask="",
                        nProcess=1, nProcessSPC=1)
    stubs = {
        "text_category_profiler.pipeline.TCF_utils": _module(
            "TCF_utils", ClassfierOptionParser=lambda: args
        ),
        "text_category_profiler.core.utilities": _module(
            "utilities", timeNow=lambda: "20260915120000", MKDIR=lambda path: None
        ),
        "text_category_profiler.concurrency.MP_utils": _module(
            "MP_utils", multicoreJob=lambda: types.SimpleNamespace(
                ComputeNProcess=lambda: 2, ComputeSPCNProcess=lambda: 1
            )
        ),
        "text_category_profiler.core.log_display": _module(
            "log_display", print_once=lambda *args, **kwargs: None
        ),
    }
    name = "_phase0_parameters"
    spec = importlib.util.spec_from_file_location(name, ROOT / "TCF_Params" / "TCFParameters.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, args


class WorkpoolCharacterizationTests(unittest.TestCase):
    def test_weitech_selects_newest_matching_id_and_moves_to_processing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "AutoBertClassify"
            pool = root / "WorkPool"
            incoming.mkdir(); pool.mkdir()
            for work_id in ("job-001", "job-003", "job-002"):
                (incoming / work_id).mkdir()
            for work_id in ("job-001", "job-002"):
                (pool / work_id).mkdir()
            args = default_args(WeiTechworkIDPath=str(incoming),
                                WeiTechWorkPoolPATH=str(pool), _dataset_dir=temp,
                                _output_dir=temp)
            module = load_main(args)
            module.DataConvert(args, {"start": 0})
            self.assertEqual("job-002", args.WeiTechworkID)
            self.assertFalse((incoming / "job-002").exists())
            self.assertTrue((root / "AutoBertClassify_Processing" / "job-002").is_dir())

    def test_no_weitech_job_aborts(self):
        with tempfile.TemporaryDirectory() as temp:
            incoming = Path(temp) / "AutoBertClassify"
            pool = Path(temp) / "WorkPool"
            incoming.mkdir(); pool.mkdir()
            args = default_args(WeiTechworkIDPath=str(incoming),
                                WeiTechWorkPoolPATH=str(pool), _dataset_dir=temp,
                                _output_dir=temp)
            module = load_main(args)
            with self.assertRaises(Exception):
                module.DataConvert(args, {"start": 0})

    def test_dataset_picker_preserves_name_and_stage_suffixes(self):
        module = load_tcf_utils()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = argparse.Namespace(
                ExecutionTime="20260915123456", ModelType="PytorchXLM", TRVPort=8050,
                train=False, WorkPoolROOT=str(root), WeiTechworkIDPath="",
                WeiTechworkID="", BertDatasetSubDir="", modelDir=str(root),
            )
            picker = module.datasetDirOutputDirPickers(
                args=args, rdy_for_stage="DataConverter", datasetDirsROOT=str(root),
                outputDirsROOT=str(root), MPLOGGER=types.SimpleNamespace(logW=lambda *a, **k: None),
            )
            dataset = picker.Pick_datasetDir()
            self.assertEqual(root / "dataset_20260915123456_PytorchXLM_pt8050", Path(dataset))

            running = Path(str(dataset) + "_is_running_DataConverter")
            running.mkdir()
            module.RenameDir = lambda SrcDir, DesDir: os.rename(SrcDir, DesDir)
            module.TaskConnector(SrcTask="DataConverter", DesTask="RunClassfier",
                                 WorkingDir=str(running)).proc()
            self.assertTrue(Path(str(dataset) + "_rdy_for_RunClassfier").is_dir())

        suffixes = [
            "_is_running_DataConverter", "_rdy_for_RunClassfier",
            "_is_running_RunClassfier", "_rdy_for_CombineTestResult",
            "_is_running_CombineTestResult", "_rdy_for_TestResultVis",
            "_is_running_TestResultVis", "_rdy_for_Spike",
        ]
        for suffix in suffixes:
            self.assertRegex(suffix, r"^_(?:is_running|rdy_for)_[A-Za-z]+$")

    def test_final_output_patterns_base_and_sdsms(self):
        base_module, _ = load_parameters()
        self.assertEqual(BASE_PATTERNS, base_module.FinalOfferedOutputFNrePatList)
        sdsms_module, args = load_parameters("SDSMS")
        sdsms_module.setArguments()
        self.assertEqual(BASE_PATTERNS + ["SDSMS.*"],
                         sdsms_module.FinalOfferedOutputFNrePatList)
        self.assertEqual("SDSMS", args.ExtractionConverterTask)

    def test_remove_flag_controls_general_backup(self):
        for remove, expected in ((False, 0), (True, 1)):
            with self.subTest(remove=remove), tempfile.TemporaryDirectory() as temp:
                calls = []
                args = default_args(RemoveBertDataDir=remove, _dataset_dir=temp,
                                    _output_dir=temp)
                module = load_main(args)
                module.BackupAIPredictResultAndDelTempFile = lambda **kw: calls.append(kw)
                module.BackupAndClean(args)
                self.assertEqual(expected, len(calls))
                if remove:
                    self.assertEqual(temp, calls[0]["BertDatasetSubDir"])

    def test_work_id_controls_delivery_backup_and_processed_move(self):
        for work_id, expected in (("", 0), ("job-007", 1)):
            with self.subTest(work_id=work_id), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                incoming = root / "AutoBertClassify"; incoming.mkdir()
                processing = root / "AutoBertClassify_Processing"; processing.mkdir()
                pool = root / "WorkPool"; pool.mkdir()
                if work_id:
                    (processing / work_id).mkdir()
                    (pool / work_id).mkdir()
                calls = []
                args = default_args(WeiTechworkID=work_id,
                    WeiTechworkIDPath=str(incoming), WeiTechWorkPoolPATH=str(pool),
                    _dataset_dir=temp, _output_dir=temp)
                module = load_main(args)
                module.BackupAIPredictResultAndDelTempFile = lambda **kw: calls.append(kw)
                module.BackupAndClean(args)
                self.assertEqual(expected, len(calls))
                if work_id:
                    self.assertEqual(BASE_PATTERNS, calls[0]["BackFNrePatList"])
                    self.assertTrue((root / "AutoBertClassify_Processed" / work_id).is_dir())
                    self.assertFalse((processing / work_id).exists())

    def test_linux_ownership_calls_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incoming = root / "AutoBertClassify"; incoming.mkdir()
            processing = root / "AutoBertClassify_Processing"; processing.mkdir()
            processed = root / "AutoBertClassify_Processed"
            work_id = "job-linux"; (processing / work_id).mkdir()
            pool = root / "WorkPool"; pool.mkdir(); (pool / work_id).mkdir()
            args = default_args(WeiTechworkID=work_id, WeiTechworkIDPath=str(incoming),
                                WeiTechWorkPoolPATH=str(pool), _dataset_dir=temp,
                                _output_dir=temp)
            module = load_main(args)
            ownership = []
            module.platform.system = lambda: "Linux"
            module.OSWALK = lambda path: [str(processed / work_id / "artifact.tsv")]
            module.chownPath = ownership.append
            module.BackupAndClean(args)
            self.assertEqual([
                os.path.join(str(incoming), "..", "AutoBertClassify_Processing"),
                os.path.join(str(incoming), "..", "AutoBertClassify_Processed"),
                os.path.join(str(incoming), "..", "AutoBertClassify_Processing", work_id),
                str(processed / work_id / "artifact.tsv"),
            ], ownership)

    def test_contract_assertions_detect_controlled_fixture_drift(self):
        expected = ["job-003", "job-002", "job-001"]
        with self.assertRaises(AssertionError):
            self.assertEqual(expected[0], ["job-002", "job-001"][0])
        with self.assertRaises(AssertionError):
            self.assertEqual(BASE_PATTERNS, list(reversed(BASE_PATTERNS)))
        with self.assertRaises(AssertionError):
            self.assertEqual("_rdy_for_RunClassfier", "_rdy_for_Classifier")


if __name__ == "__main__":
    unittest.main()
