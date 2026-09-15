import argparse
import importlib.util
import os
from pathlib import Path
import runpy
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _module(name, **attributes):
    module = types.ModuleType(name)
    vars(module).update(attributes)
    return module


def default_args(**overrides):
    values = dict(
        train=False, test=True, task="", ExecutionTime="20260915120000",
        WeiTechworkIDPath="", WeiTechWorkPoolPATH="", WeiTechworkID="",
        WeiTechFormatInputPATH="", WeiTechFormatOutputPATH="",
        WeiTechFormatSepWorkPool=False, TRVWebHost=True,
        RemoveBertDataDir=False,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class RecordingPicker:
    calls = []

    def __init__(self, args, rdy_for_stage):
        self.args = args
        self.stage = rdy_for_stage

    def proc(self):
        self.calls.append(self.stage)
        return self.args._dataset_dir, self.args._output_dir


def fake_modules(args=None, completed_codes=None, trace=None):
    args = args or default_args()
    trace = trace if trace is not None else []
    codes = iter(completed_codes or [])

    def subprocess_run(command, shell, check):
        trace.append(("command", command, shell, check))
        return types.SimpleNamespace(returncode=next(codes, 0))

    def forward(namespace):
        ignored = {"_dataset_dir", "_output_dir"}
        return "".join(f" --{key} {value}" for key, value in vars(namespace).items()
                       if value != "" and key not in ignored)

    no_op = lambda *a, **k: None
    return {
        "setproctitle": _module("setproctitle", setproctitle=no_op),
        "subprocess": _module("subprocess", run=subprocess_run),
        "TCF_Params.TCFParameters": _module(
            "TCFParameters", setArguments=lambda: args, WorkPoolROOT="WorkPool",
            BertClassfierPath="BertScript",
            FinalOfferedOutputFNrePatList=["^DFPreambleCols_df_ALL.*",
                                          "dataset_total_with_filename_FixedTest.sql3",
                                          "test.sql3", "test.tsv"],
        ),
        "text_category_profiler.core.utilities": _module(
            "utilities", OSWALK=lambda path: [], MKDIR=no_op,
            ShowElapsedTime=no_op, exit_program=lambda: trace.append(("exit",)),
            chownPath=no_op,
        ),
        "text_category_profiler.core.conformer": _module(
            "conformer", HybridConformer=lambda **kwargs: types.SimpleNamespace(proc=no_op)
        ),
        "text_category_profiler.pipeline.TCF_utils": _module(
            "TCF_utils", BackupAIPredictResultAndDelTempFile=no_op,
            convert_to_args_str=forward, datasetDirOutputDirPickers=RecordingPicker,
        ),
        "text_category_profiler.pipeline.DataConverter_utils": _module(
            "DataConverter_utils", CheckDatasetFiles=lambda path: {"test": True},
            RawAndPredictionMerger=lambda **kwargs: types.SimpleNamespace(
                proc=lambda: trace.append(("merge",))
            ),
        ),
        "text_category_profiler.concurrency.MP_utils": _module(
            "MP_utils", MPlogger=lambda **kwargs: types.SimpleNamespace(logW=no_op)
        ),
        "text_category_profiler.core.log_display": _module(
            "log_display", **{name: no_op for name in
            ("info", "print_args_summary", "print_command", "stage_banner",
             "stage_done", "stage_failed", "warning")}
        ),
    }


def load_main(args=None, completed_codes=None, trace=None):
    name = "_phase0_tcf_main"
    spec = importlib.util.spec_from_file_location(name, ROOT / "TCFMain.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake_modules(args, completed_codes, trace)):
        spec.loader.exec_module(module)
    return module


class RootPipelineCharacterizationTests(unittest.TestCase):
    def setUp(self):
        RecordingPicker.calls = []

    def test_run_stage_command_uses_legacy_shell_flags(self):
        trace = []
        module = load_main(trace=trace)
        module.run_stage_command("python stage.py --path a b", "stage")
        self.assertEqual([("command", "python stage.py --path a b", True, False)], trace)

    def test_nonzero_stage_aborts_with_command_and_code(self):
        trace = []
        module = load_main(completed_codes=[7], trace=trace)
        with self.assertRaisesRegex(RuntimeError, r"stage failed with exit code 7.*python bad.py"):
            module.run_stage_command("python bad.py", "stage")
        self.assertEqual(1, len(trace))

    def test_canonical_stage_order_for_test_run(self):
        trace = []
        with tempfile.TemporaryDirectory() as temp:
            args = default_args(_dataset_dir=temp, _output_dir=temp)
            with patch.dict(sys.modules, fake_modules(args, trace=trace)):
                runpy.run_path(str(ROOT / "TCFMain.py"), run_name="__main__")
        prefixes = [entry[1].split(" --", 1)[0] for entry in trace if entry[0] == "command"]
        self.assertEqual([
            "python DatasetConverter/DataConverter.py",
            "python BertScript/RunClassfier.py",
            "python BertScript/CombineTestResult.py",
            "python BertScript/Test_result_Vis.py",
            "python BertScript/Test_result_Vis.py",
        ], prefixes)

    def test_article_analysis_is_skipped_when_test_false(self):
        trace = []
        with tempfile.TemporaryDirectory() as temp:
            args = default_args(test=False, _dataset_dir=temp, _output_dir=temp)
            with patch.dict(sys.modules, fake_modules(args, trace=trace)):
                runpy.run_path(str(ROOT / "TCFMain.py"), run_name="__main__")
        self.assertEqual(2, sum(entry[0] == "command" for entry in trace))

    def test_sdsms_merge_is_conditional(self):
        for task, expected in (("", 0), ("SDSMS", 1), ("SDSMS_Prediction", 1)):
            with self.subTest(task=task), tempfile.TemporaryDirectory() as temp:
                trace = []
                args = default_args(task=task, _dataset_dir=temp, _output_dir=temp)
                module = load_main(args, trace=trace)
                module.ArticleAnalysis(args, {"start": 0})
                self.assertEqual(expected, trace.count(("merge",)))

    def test_stage_command_prefixes_and_forwarding(self):
        trace = []
        with tempfile.TemporaryDirectory() as temp:
            args = default_args(task="BDS", _dataset_dir=temp, _output_dir=temp)
            module = load_main(args, trace=trace)
            module.DataConvert(args, {"start": 0})
            module.RunClassfier(args, {"start": 0})
            module.CombineTestResult(args, {"start": 0})
        commands = [entry[1] for entry in trace]
        forwarded = " --train False --test True --task BDS --ExecutionTime 20260915120000 --WeiTechFormatSepWorkPool False --TRVWebHost True --RemoveBertDataDir False"
        self.assertEqual([
            "python DatasetConverter/DataConverter.py" + forwarded,
            "python BertScript/RunClassfier.py" + forwarded,
            "python BertScript/CombineTestResult.py" + forwarded,
        ], commands)

    def test_visualization_runs_base_then_weitech_command_even_when_paths_empty(self):
        trace = []
        args = default_args()
        module = load_main(args, trace=trace)
        module.TestResultVis(args, {"start": 0})
        commands = [entry[1] for entry in trace]
        self.assertEqual(2, len(commands))
        self.assertEqual(commands[0] + " -WTFSepWorkPool False", commands[1])

    def test_nonzero_aborts_before_downstream_stage(self):
        trace = []
        with tempfile.TemporaryDirectory() as temp:
            args = default_args(_dataset_dir=temp, _output_dir=temp)
            with patch.dict(sys.modules, fake_modules(args, [3], trace)):
                with self.assertRaises(RuntimeError):
                    runpy.run_path(str(ROOT / "TCFMain.py"), run_name="__main__")
        self.assertEqual(1, sum(entry[0] == "command" for entry in trace))

    def test_contract_assertions_detect_controlled_trace_drift(self):
        expected = ["DataConverter", "RunClassfier", "CombineTestResult", "Vis", "Vis"]
        drifts = [
            ["RunClassfier", "DataConverter", "CombineTestResult", "Vis", "Vis"],
            ["DataConverter", "RunClassfier", "CombineTestResult", "Vis"],
            ["DataConverter", "RunClassfier", "CombineChanged", "Vis", "Vis"],
        ]
        for drift in drifts:
            with self.subTest(drift=drift), self.assertRaises(AssertionError):
                self.assertEqual(expected, drift)


if __name__ == "__main__":
    unittest.main()
