import unittest
from types import SimpleNamespace
from unittest.mock import patch

from DatasetConverter import DataConverter
from DatasetConverter.config import default_converter_settings


def converter_args(**overrides):
    values = {
        "BertDatasetSubDir": "dataset",
        "train": True,
        "test": True,
        "debugMode": False,
        "TrainDRNDataOnly": False,
        "trainWithMaliciousDomainDataset": False,
        "FixedTestPATH": "",
        "WeiTechFormatInputPATH": "provided-input",
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


if __name__ == "__main__":
    unittest.main()
