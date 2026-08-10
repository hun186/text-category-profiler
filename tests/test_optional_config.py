import os
import sys
import tempfile
import unittest

from text_category_profiler.core.optional_config import load_optional_module
from text_category_profiler.core.optional_config import merge_module_mapping


class OptionalConfigTests(unittest.TestCase):
    def test_missing_module_leaves_mapping_unchanged(self):
        target = {"default": 1}

        module = load_optional_module("tcf_test_config_that_does_not_exist")
        loaded = merge_module_mapping(target, module, "SETTINGS")

        self.assertIsNone(module)
        self.assertFalse(loaded)
        self.assertEqual(target, {"default": 1})

    def test_existing_module_overlays_mapping(self):
        module_name = "tcf_test_optional_config"
        with tempfile.TemporaryDirectory() as temp_dir:
            module_path = os.path.join(temp_dir, module_name + ".py")
            with open(module_path, "w", encoding="utf-8") as module_file:
                module_file.write("SETTINGS = {'default': 2, 'local': 3}\n")

            sys.path.insert(0, temp_dir)
            try:
                target = {"default": 1}
                module = load_optional_module(module_name)
                loaded = merge_module_mapping(target, module, "SETTINGS")
            finally:
                sys.path.remove(temp_dir)
                sys.modules.pop(module_name, None)

        self.assertTrue(loaded)
        self.assertEqual(module.__name__, module_name)
        self.assertEqual(target, {"default": 2, "local": 3})


if __name__ == "__main__":
    unittest.main()
