import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_label_utils():
    utilities = types.ModuleType("text_category_profiler.core.utilities")
    utilities.CapWords = lambda value, **kwargs: value
    utilities.PathSEP = lambda path: "/" if "/" in path else "\\"
    utilities.pathSpliter = types.SimpleNamespace(proc=lambda path: path.replace("\\", "/").split("/"))
    utilities.OSWALK = lambda *args, **kwargs: []

    mp_utils = types.ModuleType("text_category_profiler.concurrency.MP_utils")
    mp_utils.MPlogger = types.SimpleNamespace()

    module_path = REPOSITORY_ROOT / "ClassesTree/Label_utils.py"
    spec = importlib.util.spec_from_file_location("label_utils_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(
        sys.modules,
        {
            utilities.__name__: utilities,
            mp_utils.__name__: mp_utils,
        },
    ):
        spec.loader.exec_module(module)
    return module


class FilePathLabelsPurifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.label_utils = _load_label_utils()

    def test_removes_posix_label_directory_without_doubling_separator(self):
        result = self.label_utils.FilePathLabelsPurifier.proc(
            "root/#T#[Label Name]/article.txt"
        )

        self.assertEqual(result, "root/article.txt")

    def test_removes_windows_label_directory_without_doubling_separator(self):
        result = self.label_utils.FilePathLabelsPurifier.proc(
            r"root\#T#[Label Name]\article.txt"
        )

        self.assertEqual(result, r"root\article.txt")


if __name__ == "__main__":
    unittest.main()
