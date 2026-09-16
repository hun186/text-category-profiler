import argparse
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from tests.test_tcf_main_characterization import default_args, load_main


ROOT = Path(__file__).resolve().parents[1]
BASE_PATTERNS = (
    "^DFPreambleCols_df_ALL.*",
    "dataset_total_with_filename_FixedTest.sql3",
    "test.sql3",
    "test.tsv",
)


def _module(name, **attributes):
    module = types.ModuleType(name)
    vars(module).update(attributes)
    return module


def configuration_module():
    from text_category_profiler.pipeline import configuration
    return configuration


def namespace(**overrides):
    values = dict(
        debugMode=False,
        TrainDRNDataOnly=False,
        trainWithMaliciousDomainDataset=False,
        WeiTechworkIDPath=r"incoming\jobs",
        WeiTechFormatInputPATH="",
        ExecutionTime="",
        task="",
        ExtractionConverterTask="",
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class RecordingFileSystem:
    def __init__(self):
        self.calls = []

    def rename(self, source, destination):
        self.calls.append(("rename", source, destination))
        Path(source).rename(destination)

    def make_directory(self, path):
        self.calls.append(("mkdir", path))
        Path(path).mkdir(parents=True, exist_ok=True)


class PipelineConfigurationTests(unittest.TestCase):
    def test_import_does_not_parse_process_argv(self):
        effects = []
        parser_module = _module(
            "TCF_utils",
            ClassfierOptionParser=lambda *args, **kwargs: effects.append("parse"),
        )
        utilities = _module(
            "utilities",
            timeNow=lambda: effects.append("clock"),
            MKDIR=lambda path: effects.append(("mkdir", path)),
        )
        concurrency = _module(
            "MP_utils",
            multicoreJob=lambda: effects.append("process"),
        )
        display = _module(
            "log_display",
            print_once=lambda *args, **kwargs: effects.append("print"),
        )
        stubs = {
            "text_category_profiler.pipeline.TCF_utils": parser_module,
            "text_category_profiler.core.utilities": utilities,
            "text_category_profiler.concurrency.MP_utils": concurrency,
            "text_category_profiler.core.log_display": display,
        }
        spec = importlib.util.spec_from_file_location(
            "_task5_parameters", ROOT / "TCF_Params" / "TCFParameters.py"
        )
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)
        self.assertEqual([], effects)
        self.assertEqual(list(BASE_PATTERNS), module.FinalOfferedOutputFNrePatList)

    def test_build_pipeline_plan_has_no_filesystem_or_process_side_effects(self):
        configuration = configuration_module()
        effects = []
        args = namespace()
        plan = configuration.build_pipeline_plan(
            argv=["ignored"],
            parser=lambda argv: args,
            clock=lambda: "20260916112233",
            platform_name=lambda: "Linux",
            filesystem=types.SimpleNamespace(
                rename=lambda *values: effects.append(("rename", values)),
                make_directory=lambda path: effects.append(("mkdir", path)),
            ),
            process_source=lambda: effects.append("process"),
        )
        self.assertEqual([], effects)
        self.assertEqual("20260916112233", plan.args.ExecutionTime)
        self.assertEqual("incoming/jobs", plan.args.WeiTechworkIDPath)
        self.assertIsNot(args, plan.args)

    def test_sdsms_plan_owns_fresh_output_patterns(self):
        configuration = configuration_module()
        first = configuration.build_pipeline_plan(
            parser=lambda argv: namespace(task="SDSMS"),
            clock=lambda: "NOW",
            platform_name=lambda: "Linux",
        )
        second = configuration.build_pipeline_plan(
            parser=lambda argv: namespace(task="SDSMS_Prediction"),
            clock=lambda: "NOW",
            platform_name=lambda: "Linux",
        )
        normal = configuration.build_pipeline_plan(
            parser=lambda argv: namespace(),
            clock=lambda: "NOW",
            platform_name=lambda: "Linux",
        )
        self.assertEqual(BASE_PATTERNS + ("SDSMS.*",), first.final_output_patterns)
        self.assertEqual(BASE_PATTERNS + ("SDSMS.*",), second.final_output_patterns)
        self.assertEqual(BASE_PATTERNS, normal.final_output_patterns)
        self.assertIsNot(first.args, second.args)
        self.assertEqual("SDSMS", first.args.ExtractionConverterTask)

    def test_activation_renames_weitech_input_and_discovers_process_counts(self):
        configuration = configuration_module()
        with tempfile.TemporaryDirectory() as temp:
            input_path = Path(temp) / "incoming"
            input_path.mkdir()
            plan = configuration.build_pipeline_plan(
                parser=lambda argv: namespace(
                    WeiTechFormatInputPATH=str(input_path),
                    ExecutionTime="EXPLICIT",
                ),
                clock=lambda: self.fail("explicit ExecutionTime must be preserved"),
                platform_name=lambda: "Linux",
            )
            filesystem = RecordingFileSystem()
            processes = types.SimpleNamespace(
                ComputeNProcess=lambda: 7,
                ComputeSPCNProcess=lambda: 3,
            )
            context = configuration.activate_pipeline_runtime(
                plan, filesystem=filesystem, process_source=lambda: processes
            )
        renamed = str(input_path) + "_EXPLICIT_is_running_AI"
        self.assertEqual(renamed, context.args.WeiTechFormatInputPATH)
        self.assertEqual(7, context.args.nProcess)
        self.assertEqual(3, context.args.nProcessSPC)
        self.assertEqual(
            [("rename", str(input_path), renamed), ("mkdir", str(input_path))],
            filesystem.calls,
        )

    def test_root_path_policy_matches_legacy_modes(self):
        configuration = configuration_module()
        cases = (
            (dict(debugMode=True), "Windows", ("TopicTextCrawler/TrainSamples",), "debug"),
            (dict(TrainDRNDataOnly=True), "Windows", ("===DRNData",), "TrainDRNDataOnly"),
            (dict(trainWithMaliciousDomainDataset=True), "Linux", None,
             "linux+trainWithMaliciousDomainDataset"),
            ({}, "Windows", ("TrainSamples",), "debug"),
        )
        for overrides, system, expected_roots, expected_mode in cases:
            with self.subTest(overrides=overrides, system=system):
                plan = configuration.build_pipeline_plan(
                    parser=lambda argv, values=overrides: namespace(**values),
                    clock=lambda: "NOW",
                    platform_name=lambda value=system: value,
                )
                if expected_roots is not None:
                    self.assertEqual(expected_roots, plan.root_paths)
                else:
                    self.assertEqual("惡意網址分析", plan.root_paths[-1])
                self.assertEqual(expected_mode, plan.run_mode)

    def test_legacy_set_arguments_returns_namespace(self):
        import TCF_Params.TCFParameters as parameters

        with patch.object(
            parameters, "ClassfierOptionParser", return_value=namespace()
        ), patch.object(parameters, "timeNow", return_value="20260916120000"), patch.object(
            parameters, "multicoreJob", return_value=types.SimpleNamespace(
                ComputeNProcess=lambda: 4, ComputeSPCNProcess=lambda: 2
            )
        ):
            args = parameters.setArguments([])
        self.assertIsInstance(args, argparse.Namespace)
        self.assertEqual("20260916120000", args.ExecutionTime)
        self.assertEqual((4, 2), (args.nProcess, args.nProcessSPC))

    def test_delivery_receives_task_owned_output_patterns(self):
        for task, expected in (
            ("", list(BASE_PATTERNS)),
            ("SDSMS", list(BASE_PATTERNS) + ["SDSMS.*"]),
            ("SDSMS_Prediction", list(BASE_PATTERNS) + ["SDSMS.*"]),
        ):
            with self.subTest(task=task), tempfile.TemporaryDirectory() as temp:
                calls = []
                args = default_args(
                    task=task,
                    WeiTechworkID="job",
                    WeiTechworkIDPath=str(Path(temp) / "incoming"),
                    WeiTechWorkPoolPATH=str(Path(temp) / "pool"),
                    _dataset_dir=temp,
                    _output_dir=temp,
                )
                processing = Path(temp) / "AutoBertClassify_Processing" / "job"
                processing.mkdir(parents=True)
                (Path(temp) / "pool" / "job").mkdir(parents=True)
                module = load_main(args)
                module.MKDIR = lambda path: Path(path).mkdir(
                    parents=True, exist_ok=True
                )
                module.BackupAIPredictResultAndDelTempFile = (
                    lambda **kwargs: calls.append(kwargs)
                )
                module.BackupAndClean(args)
                self.assertEqual(expected, calls[0]["BackFNrePatList"])


if __name__ == "__main__":
    unittest.main()
