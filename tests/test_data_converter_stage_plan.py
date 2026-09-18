import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from DatasetConverter import DataConverter
from DatasetConverter import stage
from DatasetConverter.config import default_converter_settings
from DatasetConverter.config import ConfigValidationError
from DatasetConverter.config import RuntimeConfig


def converter_args(**overrides):
    values = {
        "BertDatasetSubDir": "dataset",
        "datasetDataBaseSubDir": "datasetDB",
        "train": True,
        "test": True,
        "debugMode": False,
        "TrainDRNDataOnly": False,
        "trainWithMaliciousDomainDataset": False,
        "FixedTestPATH": "",
        "WeiTechFormatInputPATH": "provided-input",
        "WeiTechworkID": "",
        "WeiTechWorkPoolPATH": "",
        "ExtractionConverterTask": "",
        "FixedTestFileBound": 12,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class DataConverterStagePlanTests(unittest.TestCase):
    def test_runtime_process_policy_preserves_explicit_child_options(self):
        process_source = SimpleNamespace(
            ComputeNProcess=lambda log=False: 19,
            ComputeSPCNProcess=lambda log=False: 4,
        )
        cases = (
            ([], 1, 1, 19, 4),
            (["--nProcess", "1", "--nProcessSPC", "1"], 1, 1, 1, 1),
            (["-nProc", "3"], 3, 1, 3, 4),
            (["-nProcSPC", "2"], 1, 2, 19, 2),
        )
        for argv, parsed_workers, parsed_large, expected_workers, expected_large in cases:
            with self.subTest(argv=argv):
                config = DataConverter.resolve_runtime_config(
                    SimpleNamespace(
                        nProcess=parsed_workers,
                        nProcessSPC=parsed_large,
                    ),
                    argv,
                    process_source=process_source,
                )
                self.assertEqual(
                    RuntimeConfig(expected_workers, expected_large), config
                )

    def test_dataset_generator_propagates_processes_to_secondary_readers(self):
        reader_calls = []

        class FakeSeries:
            def dropna(self):
                return self

            def nunique(self):
                return 0

        class FakeFrame:
            shape = (0, 1)
            empty = True

            def __len__(self):
                return 0

            def __getitem__(self, key):
                return FakeSeries()

        def record_reader(**kwargs):
            reader_calls.append((kwargs["sourceRole"], kwargs.get("nProcess", 1)))
            return FakeFrame()

        generator = DataConverter.DatasetGenerator(
            df=FakeFrame(),
            OUTPUTMAIN="output",
            IndexCols=[],
            datasetSubDir="dataset",
            DatasetRatio={"Train": 0.7, "Validation": 0.2, "Test": 0.1},
            FixedTestPATHList=["fixed"],
            esJob={"indexname": "example"},
            DCkwargs={},
            nProcess=7,
            MPLOGGER=object(),
        )
        with (
            patch.object(DataConverter, "discover_source_spec", return_value=["fixed.txt"]),
            patch.object(DataConverter, "deduplicate_dataset_rows", side_effect=lambda frame: frame),
            patch.object(
                DataConverter,
                "iter_dataset_splits",
                return_value=[("train", FakeFrame()), ("test", FakeFrame())],
            ),
            patch.object(DataConverter, "BuildSamplesDfFromPaths", side_effect=record_reader),
            patch.object(DataConverter, "empty_dataframe", return_value=FakeFrame()),
            patch.object(DataConverter, "concat_dataframes", return_value=FakeFrame()),
            patch.object(DataConverter, "dfOutputer", return_value=SimpleNamespace(run=lambda: None)),
            patch.object(DataConverter, "multicoreJob", return_value=SimpleNamespace(run=lambda: [])),
            patch.object(DataConverter, "key_values"),
            patch("builtins.open", unittest.mock.mock_open()),
        ):
            generator.run()

        self.assertEqual(
            [("fixed test source", 7), ("Elasticsearch source", 7)],
            reader_calls,
        )

    def test_job_generator_resolves_empty_tokenizer_model_directory(self):
        args = SimpleNamespace(ModelType="bert", MaxSeqLength=128)

        with (
            patch.object(DataConverter, "info") as info,
            patch.object(
                DataConverter,
                "pick_dataset_directories",
                return_value=("dataset", "resolved-model"),
            ) as pick_dataset_directories,
            patch.object(
                DataConverter.DataConvertJobGenerater,
                "BuildFileList",
                return_value=[],
            ),
            patch.object(
                DataConverter.DataConvertJobGenerater,
                "BuildLabelConvertDict",
                return_value={},
            ),
            patch.object(DataConverter.DataConvertJobGenerater, "show"),
            patch.object(DataConverter, "key_values"),
        ):
            job = DataConverter.DataConvertJobGenerater(
                fileList=["input.txt"],
                tokenizationWrap=True,
                modelDir="",
                cli_args=args,
                MPLOGGER=object(),
            )

        info.assert_called_once()
        pick_dataset_directories.assert_called_once_with(
            args=args,
            ready_for_stage="DataConverter",
        )
        self.assertEqual(job.modelDir, "resolved-model")

    def test_normalization_returns_a_plan_without_runtime_activation(self):
        args = converter_args()
        settings = default_converter_settings()

        with (
            patch.object(stage, "parse_converter_options", return_value=args),
            patch.object(
                stage,
                "pick_dataset_directories",
                return_value=("normalized-dataset", "unused-output"),
            ),
            patch.object(
                stage,
                "fixed_test_paths",
                return_value=["fixed-a", "fixed-b"],
            ),
            patch.object(stage, "make_directory") as make_directory,
            patch.object(stage, "create_logger") as create_logger,
            patch.object(stage, "stage_banner") as stage_banner,
        ):
            plan = DataConverter.normalize_stage_plan(settings, argv=["--example"])

        self.assertIsInstance(plan, DataConverter.StagePlan)
        self.assertIsInstance(plan.source_config, stage.SourceConfig)
        self.assertIsInstance(plan.mode_config, stage.ModeConfig)
        self.assertEqual(plan.mode_config.source_mode, plan.source_config.mode)
        self.assertIsNone(plan.workspace_config.work_item_directory)
        self.assertEqual(plan.work_directory, "normalized-dataset_is_running_DataConverter")
        self.assertEqual(
            plan.fixed_test_paths,
            ["fixed-a", "fixed-b", "provided-input"],
        )
        self.assertEqual(
            plan.root_paths,
            list(stage.source_config_from_namespace(args).root_paths),
        )
        self.assertEqual(plan.converter_settings["FixedTestFileBound"], 12)
        self.assertEqual(plan.output_config.dataset_directory, "normalized-dataset_is_running_DataConverter")
        self.assertEqual(
            plan.output_config.output_main,
            os.path.join(
                "normalized-dataset_is_running_DataConverter",
                "datasetDB",
                "dataset_total_with_filename",
            ),
        )
        self.assertEqual(
            plan.output_config.labels_count_output,
            os.path.join(
                "normalized-dataset_is_running_DataConverter",
                "datasetDB",
                "dataset_total_labels_count",
            ),
        )
        self.assertEqual(
            plan.output_config.fixed_test_output,
            os.path.join(
                "normalized-dataset_is_running_DataConverter",
                "datasetDB",
                "dataset_total_with_filename_FixedTest",
            ),
        )
        self.assertEqual(
            plan.converter_config.split.as_legacy_mapping(),
            {"Train": 0.7, "Validation": 0.2, "Test": 0.1},
        )
        self.assertNotIn("FixedTestFileBound", settings)
        returned_settings = plan.converter_settings
        returned_settings["sampleMethod"]["nBound"]["default"] = 1
        self.assertEqual(
            plan.converter_settings["sampleMethod"]["nBound"]["default"],
            5000,
        )
        returned_roots = plan.root_paths
        returned_roots.append("mutated-copy")
        self.assertNotIn("mutated-copy", plan.source_config.root_paths)
        make_directory.assert_not_called()
        create_logger.assert_not_called()
        stage_banner.assert_not_called()

    def test_non_test_plan_clears_fixed_test_argument_without_discovery(self):
        args = converter_args(test=False, FixedTestPATH="ignored")

        with (
            patch.object(stage, "parse_converter_options", return_value=args),
            patch.object(
                stage,
                "pick_dataset_directories",
                return_value=("dataset", "output"),
            ),
            patch.object(stage, "fixed_test_paths") as fixed_test_paths,
        ):
            plan = DataConverter.normalize_stage_plan(
                default_converter_settings(),
                argv=[],
            )

        fixed_test_paths.assert_not_called()
        self.assertEqual(plan.fixed_test_paths, ["ignored", "provided-input"])
        self.assertEqual(plan.args.FixedTestPATH, "")

    def test_runtime_config_is_validated_before_activation_side_effects(self):
        args = converter_args()
        with (
            patch.object(stage, "parse_converter_options", return_value=args),
            patch.object(
                stage,
                "pick_dataset_directories",
                return_value=("dataset", "output"),
            ),
            patch.object(stage, "fixed_test_paths", return_value=[]),
        ):
            plan = DataConverter.normalize_stage_plan(
                default_converter_settings(),
                argv=[],
            )

        with (
            patch.object(stage, "make_directory") as make_directory,
            patch.object(stage, "create_logger") as create_logger,
            patch.object(stage, "stage_banner") as stage_banner,
            self.assertRaisesRegex(ConfigValidationError, "RuntimeConfig"),
        ):
            DataConverter.activate_stage_context(plan, runtime_config=None)

        make_directory.assert_not_called()
        create_logger.assert_not_called()
        stage_banner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
