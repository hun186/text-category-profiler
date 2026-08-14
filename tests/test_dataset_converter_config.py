import unittest
from dataclasses import FrozenInstanceError

from DatasetConverter.config import DEFAULT_SPLIT_CONFIG
from DatasetConverter.config import default_converter_settings


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


if __name__ == "__main__":
    unittest.main()
