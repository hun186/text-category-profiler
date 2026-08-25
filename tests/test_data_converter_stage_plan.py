import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from DatasetConverter import DataConverter
from DatasetConverter.config import default_converter_settings
from DatasetConverter.config import ConfigValidationError


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
    def test_normalization_returns_a_plan_without_runtime_activation(self):
        args = converter_args()
        settings = default_converter_settings()

        with (
            patch.object(DataConverter, "parse_converter_options", return_value=args),
            patch.object(
                DataConverter,
                "pick_dataset_directories",
                return_value=("normalized-dataset", "unused-output"),
            ),
            patch.object(
                DataConverter,
                "fixed_test_paths",
                return_value=["fixed-a", "fixed-b"],
            ),
            patch.object(DataConverter, "make_directory") as make_directory,
            patch.object(DataConverter, "MPlogger") as create_logger,
            patch.object(DataConverter, "stage_banner") as stage_banner,
        ):
            plan = DataConverter.normalize_stage_plan(settings, argv=["--example"])

        self.assertIsInstance(plan, DataConverter.StagePlan)
        self.assertIsInstance(plan.source_config, DataConverter.SourceConfig)
        self.assertIsInstance(plan.mode_config, DataConverter.ModeConfig)
        self.assertEqual(plan.mode_config.source_mode, plan.source_config.mode)
        self.assertIsNone(plan.workspace_config.work_item_directory)
        self.assertEqual(plan.work_directory, "normalized-dataset_is_running_DataConverter")
        self.assertEqual(
            plan.fixed_test_paths,
            ["fixed-a", "fixed-b", "provided-input"],
        )
        self.assertEqual(
            plan.root_paths,
            list(DataConverter.source_config_from_namespace(args).root_paths),
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
            patch.object(DataConverter, "parse_converter_options", return_value=args),
            patch.object(
                DataConverter,
                "pick_dataset_directories",
                return_value=("dataset", "output"),
            ),
            patch.object(DataConverter, "fixed_test_paths") as fixed_test_paths,
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
            patch.object(DataConverter, "parse_converter_options", return_value=args),
            patch.object(
                DataConverter,
                "pick_dataset_directories",
                return_value=("dataset", "output"),
            ),
            patch.object(DataConverter, "fixed_test_paths", return_value=[]),
        ):
            plan = DataConverter.normalize_stage_plan(
                default_converter_settings(),
                argv=[],
            )

        with (
            patch.object(DataConverter, "make_directory") as make_directory,
            patch.object(DataConverter, "MPlogger") as create_logger,
            patch.object(DataConverter, "stage_banner") as stage_banner,
            self.assertRaisesRegex(ConfigValidationError, "RuntimeConfig"),
        ):
            DataConverter.activate_stage_context(plan, runtime_config=None)

        make_directory.assert_not_called()
        create_logger.assert_not_called()
        stage_banner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
