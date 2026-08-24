import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

from DatasetConverter.config import DEFAULT_SPLIT_CONFIG
from DatasetConverter.config import default_converter_settings
from DatasetConverter.config import root_paths_from_namespace
from DatasetConverter.config import SourceMode
from DatasetConverter.config import source_config_from_namespace
from DatasetConverter.config import ConfigValidationError
from DatasetConverter.config import ConverterConfig


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


if __name__ == "__main__":
    unittest.main()
