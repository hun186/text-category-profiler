import os
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from DatasetConverter.config import DEFAULT_SPLIT_CONFIG
from DatasetConverter.config import default_converter_settings
from DatasetConverter.config import root_paths_from_namespace
from DatasetConverter.config import SourceMode
from DatasetConverter.config import source_config_from_namespace
from DatasetConverter.config import SourceConfig
from DatasetConverter.config import ConfigValidationError
from DatasetConverter.config import ConverterConfig
from DatasetConverter.config import SplitConfig
from DatasetConverter.config import OutputConfig
from DatasetConverter.config import RuntimeConfig
from DatasetConverter.config import ModeConfig
from DatasetConverter.config import WorkMode
from DatasetConverter.config import mode_config_from_namespace
from DatasetConverter.config import WorkspaceConfig
from DatasetConverter.config import workspace_config_from_namespace


class DatasetConverterConfigTests(unittest.TestCase):
    def test_default_settings_preserve_active_legacy_values(self):
        settings = default_converter_settings()

        self.assertEqual(settings["WIDTH"], 256)
        self.assertEqual(settings["ConvertToSpec"], "tw2sp")
        self.assertEqual(settings["sampleMethod"]["nBound"]["Scrap"], 200)
        self.assertEqual(settings["sampleMethod"]["LenLBD"], 1)
        self.assertTrue(settings["RBActive"])

    def test_default_settings_do_not_share_nested_mutable_state(self):
        first = default_converter_settings()
        second = default_converter_settings()

        first["sampleMethod"]["nBound"]["default"] = 1
        first["DataCleanerRePatternDict"]["&nbsp Remover"]["SrcPat"].append(
            "changed"
        )

        self.assertEqual(second["sampleMethod"]["nBound"]["default"], 5000)
        self.assertNotIn(
            "changed",
            second["DataCleanerRePatternDict"]["&nbsp Remover"]["SrcPat"],
        )

    def test_split_config_is_immutable_and_returns_fresh_legacy_mappings(self):
        with self.assertRaises(FrozenInstanceError):
            DEFAULT_SPLIT_CONFIG.train = 0.5

        first = DEFAULT_SPLIT_CONFIG.as_legacy_mapping()
        second = DEFAULT_SPLIT_CONFIG.as_legacy_mapping()
        first["Train"] = 0

        self.assertEqual(second, {"Train": 0.7, "Validation": 0.2, "Test": 0.1})

    def test_split_config_rejects_invalid_ratios(self):
        invalid_ratios = (
            ({"train": -0.1, "validation": 0.5, "test": 0.6}, "Train"),
            ({"train": True, "validation": 0.0, "test": 0.0}, "Train"),
            ({"train": float("inf"), "validation": 0.0, "test": 0.0}, "Train"),
            ({"train": 0.6, "validation": 0.3, "test": 0.2}, "sum"),
        )
        for values, message in invalid_ratios:
            with self.subTest(values=values):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    SplitConfig(**values)

    def test_root_path_policy_preserves_legacy_modes(self):
        args = SimpleNamespace(
            train=True,
            debugMode=False,
            TrainDRNDataOnly=False,
            trainWithMaliciousDomainDataset=False,
        )

        linux_roots = root_paths_from_namespace(args, system_name="Linux")
        self.assertIn("News/THUCNews", linux_roots)
        self.assertIn("C_wikisourcePortal", linux_roots)
        self.assertNotIn("惡意網址分析", linux_roots)

        args.trainWithMaliciousDomainDataset = True
        self.assertEqual(
            root_paths_from_namespace(args, system_name="Linux")[-1],
            "惡意網址分析",
        )

        args.debugMode = True
        self.assertEqual(
            root_paths_from_namespace(args, system_name="Linux"),
            ("TopicTextCrawler/TrainSamples",),
        )

    def test_root_path_policy_handles_training_gates_and_non_linux(self):
        args = SimpleNamespace(
            train=True,
            debugMode=False,
            TrainDRNDataOnly=True,
            trainWithMaliciousDomainDataset=False,
        )
        self.assertEqual(
            root_paths_from_namespace(args, system_name="Windows"),
            ("===DRNData",),
        )

        args.TrainDRNDataOnly = False
        self.assertEqual(
            root_paths_from_namespace(args, system_name="Windows"),
            ("TrainSamples",),
        )

        args.train = False
        self.assertEqual(root_paths_from_namespace(args, system_name="Linux"), ())

    def test_source_config_is_typed_immutable_and_copies_fixed_test_paths(self):
        args = SimpleNamespace(
            train=True,
            test=True,
            debugMode=False,
            TrainDRNDataOnly=False,
            trainWithMaliciousDomainDataset=True,
        )
        fixed_test_paths = ["fixed-a"]

        config = source_config_from_namespace(
            args,
            fixed_test_paths=tuple(fixed_test_paths),
            system_name="Linux",
        )
        fixed_test_paths.append("changed")

        self.assertEqual(config.mode, SourceMode.LINUX_WITH_MALICIOUS_DOMAIN)
        self.assertTrue(config.training_enabled)
        self.assertTrue(config.test_enabled)
        self.assertEqual(config.fixed_test_paths, ("fixed-a",))
        with self.assertRaises(FrozenInstanceError):
            config.mode = SourceMode.DEBUG

    def test_mode_config_preserves_source_priority_and_weitech_activation(self):
        args = SimpleNamespace(
            train=True,
            test=True,
            debugMode=True,
            TrainDRNDataOnly=True,
            trainWithMaliciousDomainDataset=True,
            WeiTechworkID="work-1",
            ExtractionConverterTask="extract-task",
        )
        source_config = source_config_from_namespace(args, system_name="Linux")
        config = mode_config_from_namespace(args, source_config)

        self.assertIsInstance(config, ModeConfig)
        self.assertEqual(config.source_mode, SourceMode.DEBUG)
        self.assertEqual(config.work_mode, WorkMode.WEITECH_EXTRACTION)
        self.assertTrue(config.extraction_enabled)
        with self.assertRaises(FrozenInstanceError):
            config.work_mode = WorkMode.STANDARD

    def test_mode_config_preserves_ignored_extraction_without_weitech_work_id(self):
        args = SimpleNamespace(
            WeiTechworkID="",
            ExtractionConverterTask="ignored-by-legacy-flow",
        )
        source_config = SourceConfig(
            root_paths=(),
            fixed_test_paths=(),
            mode=SourceMode.TRAINING_DISABLED,
            training_enabled=False,
            test_enabled=True,
        )

        config = mode_config_from_namespace(args, source_config)

        self.assertEqual(config.work_mode, WorkMode.STANDARD)
        self.assertFalse(config.extraction_enabled)
        self.assertEqual(config.extraction_task, "ignored-by-legacy-flow")

    def test_mode_config_rejects_invalid_workspace_values(self):
        source_config = SourceConfig(
            root_paths=(),
            fixed_test_paths=(),
            mode=SourceMode.TRAINING_DISABLED,
            training_enabled=False,
            test_enabled=False,
        )
        for name, value, message in (
            ("WeiTechworkID", None, "string"),
            ("ExtractionConverterTask", "bad\0task", "null"),
        ):
            args = SimpleNamespace(WeiTechworkID="", ExtractionConverterTask="")
            setattr(args, name, value)
            with self.subTest(name=name):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    mode_config_from_namespace(args, source_config)

        args = SimpleNamespace(WeiTechworkID="", ExtractionConverterTask="")
        with self.assertRaisesRegex(ConfigValidationError, "SourceConfig"):
            mode_config_from_namespace(args, None)

    def test_workspace_config_builds_a_bounded_weitech_work_item_path(self):
        mode_config = ModeConfig(
            source_mode=SourceMode.TRAINING_DISABLED,
            work_mode=WorkMode.WEITECH,
            wei_tech_work_id="work-1",
            extraction_task="",
        )
        args = SimpleNamespace(WeiTechWorkPoolPATH="work-pool")

        config = workspace_config_from_namespace(args, mode_config)

        self.assertEqual(config.work_pool_directory, "work-pool")
        self.assertEqual(
            config.work_item_directory,
            os.path.join("work-pool", "work-1"),
        )
        with self.assertRaises(FrozenInstanceError):
            config.work_id = "changed"

    def test_workspace_config_allows_an_inactive_empty_workspace(self):
        config = WorkspaceConfig(work_pool_directory="", work_id="")

        self.assertIsNone(config.work_item_directory)

    def test_workspace_config_rejects_missing_pool_and_unsafe_work_ids(self):
        invalid_values = (
            ({"work_pool_directory": "", "work_id": "work-1"}, "required"),
            ({"work_pool_directory": "pool", "work_id": ".."}, "component"),
            ({"work_pool_directory": "pool", "work_id": "nested/work"}, "component"),
            ({"work_pool_directory": "pool\0bad", "work_id": "work"}, "null"),
        )
        for values, message in invalid_values:
            with self.subTest(values=values):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    WorkspaceConfig(**values)

    def test_output_config_preserves_canonical_artifact_paths(self):
        config = OutputConfig(
            dataset_directory="work_is_running_DataConverter",
            database_subdirectory="datasetDB",
        )

        self.assertEqual(
            config.database_directory,
            os.path.join("work_is_running_DataConverter", "datasetDB"),
        )
        self.assertEqual(
            config.output_main,
            os.path.join(
                "work_is_running_DataConverter",
                "datasetDB",
                "dataset_total_with_filename",
            ),
        )
        self.assertEqual(
            config.labels_count_output,
            os.path.join(
                "work_is_running_DataConverter",
                "datasetDB",
                "dataset_total_labels_count",
            ),
        )
        self.assertEqual(
            config.fixed_test_output,
            os.path.join(
                "work_is_running_DataConverter",
                "datasetDB",
                "dataset_total_with_filename_FixedTest",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            config.dataset_directory = "changed"

    def test_output_config_rejects_invalid_paths_before_activation(self):
        invalid_values = (
            ({"dataset_directory": "", "database_subdirectory": "db"}, "empty"),
            ({"dataset_directory": "work\0bad", "database_subdirectory": "db"}, "null"),
            ({"dataset_directory": "work", "database_subdirectory": None}, "string"),
        )
        for values, message in invalid_values:
            with self.subTest(values=values):
                with self.assertRaisesRegex(ConfigValidationError, message):
                    OutputConfig(**values)

    def test_runtime_config_is_immutable_and_rejects_invalid_process_counts(self):
        config = RuntimeConfig(worker_processes=4, large_output_processes=2)

        self.assertEqual(config.worker_processes, 4)
        self.assertEqual(config.large_output_processes, 2)
        with self.assertRaises(FrozenInstanceError):
            config.worker_processes = 1

        invalid_counts = (0, -1, True, 1.5, "2")
        for value in invalid_counts:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ConfigValidationError, "positive integer"):
                    RuntimeConfig(
                        worker_processes=value,
                        large_output_processes=1,
                    )

    def test_converter_config_owns_frozen_settings_and_returns_fresh_legacy_copies(self):
        settings = default_converter_settings()
        config = ConverterConfig.from_legacy_settings(
            settings,
            fixed_test_file_bound=25,
        )

        settings["sampleMethod"]["nBound"]["default"] = 1
        first = config.as_legacy_mapping()
        second = config.as_legacy_mapping()
        first["sampleMethod"]["nBound"]["default"] = 2

        self.assertEqual(config.width, 256)
        self.assertEqual(config.fixed_test_file_bound, 25)
        self.assertIs(config.split, DEFAULT_SPLIT_CONFIG)
        self.assertEqual(
            config.split.as_legacy_mapping(),
            {"Train": 0.7, "Validation": 0.2, "Test": 0.1},
        )
        self.assertEqual(second["sampleMethod"]["nBound"]["default"], 5000)
        with self.assertRaises(TypeError):
            config.reader_settings["sampleMethod"] = {}

    def test_converter_config_rejects_invalid_core_settings(self):
        invalid_width = default_converter_settings()
        invalid_width["WIDTH"] = 0
        with self.assertRaisesRegex(ConfigValidationError, "WIDTH"):
            ConverterConfig.from_legacy_settings(
                invalid_width,
                fixed_test_file_bound=0,
            )

        with self.assertRaisesRegex(ConfigValidationError, "FixedTestFileBound"):
            ConverterConfig.from_legacy_settings(
                default_converter_settings(),
                fixed_test_file_bound=-1,
            )

        with self.assertRaisesRegex(ConfigValidationError, "SplitConfig"):
            ConverterConfig.from_legacy_settings(
                default_converter_settings(),
                fixed_test_file_bound=0,
                split=None,
            )


if __name__ == "__main__":
    unittest.main()
