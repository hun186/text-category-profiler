import ast
import unittest
from pathlib import Path

from DatasetConverter.reader_utils import filename_extension
from DatasetConverter.reader_utils import intersect_lists
from DatasetConverter.reader_utils import normalize_filename
from DatasetConverter.reader_utils import sanitize_filename
from DatasetConverter.reader_utils import wrap_text


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ReaderUtilsTests(unittest.TestCase):
    def test_normalizes_windows_separators(self):
        self.assertEqual(normalize_filename(r"model\checkpoint"), "model/checkpoint")

    def test_extracts_extension_with_optional_lowercase(self):
        self.assertEqual(filename_extension("folder/sample.TXT"), "TXT")
        self.assertEqual(filename_extension("folder/sample.TXT", lower=True), "txt")

    def test_sanitizes_legacy_filename_characters(self):
        self.assertEqual(sanitize_filename("a/b:'c\n"), "a_b_’c_")

    def test_preserves_legacy_set_intersection_contract(self):
        self.assertEqual(set(intersect_lists(["a", "b"], ["b", "c"])), {"b"})

    def test_wraps_text_with_legacy_piece_limit(self):
        self.assertEqual(wrap_text("abcdef", 2), ["ab", "cd", "ef"])
        self.assertEqual(wrap_text("abcdef", 2, piece_limit=2), ["ab", "cd"])

    def test_reader_no_longer_imports_generic_utilities(self):
        path = REPOSITORY_ROOT / "DatasetConverter" / "sampleHandler.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        self.assertFalse(
            any(
                isinstance(node, ast.ImportFrom)
                and node.module == "text_category_profiler.core.utilities"
                for node in tree.body
            )
        )


if __name__ == "__main__":
    unittest.main()
