import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class LoadDatasetCountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = Path("text_category_profiler/pipeline/TCF_utils.py")
        source = source_path.read_text(encoding="utf-8")
        function = next(
            node for node in ast.parse(source).body
            if isinstance(node, ast.FunctionDef) and node.name == "LoadDatasetCount")
        namespace = {
            "OSWALK": lambda root: [
                os.path.join(directory, filename)
                for directory, _, filenames in os.walk(root)
                for filename in filenames
            ],
            "getFNFromFullPath": os.path.basename,
            "dfFromSQLite3": mock.Mock(),
        }
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     str(source_path), "exec"), namespace)
        cls.load_dataset_count = staticmethod(namespace["LoadDatasetCount"])
        cls.sqlite_loader = namespace["dfFromSQLite3"]

    def setUp(self):
        self.sqlite_loader.reset_mock()

    def test_canonical_count_wins_when_both_counts_exist(self):
        with tempfile.TemporaryDirectory() as output_dir:
            canonical = Path(output_dir, "dataset_total_labels_count.sql3")
            fixed_test = Path(output_dir, "dataset_total_FixedTest_labels_count.sql3")
            canonical.touch()
            fixed_test.touch()
            canonical_frame = mock.Mock()
            canonical_indexed = mock.Mock()
            canonical_frame.set_index.return_value = canonical_indexed

            self.sqlite_loader.return_value = canonical_frame
            result = self.load_dataset_count(output_dir)

            self.assertIs(result, canonical_indexed)
            self.sqlite_loader.assert_called_once_with(str(canonical))
            canonical_frame.set_index.assert_called_once_with("index")

    def test_fixed_test_count_is_used_when_canonical_count_is_absent(self):
        with tempfile.TemporaryDirectory() as output_dir:
            fixed_test = Path(output_dir, "dataset_total_FixedTest_labels_count.sql3")
            fixed_test.touch()
            fixed_test_frame = mock.Mock()
            fixed_test_indexed = mock.Mock()
            fixed_test_frame.set_index.return_value = fixed_test_indexed

            self.sqlite_loader.return_value = fixed_test_frame
            result = self.load_dataset_count(output_dir)

            self.assertIs(result, fixed_test_indexed)
            self.sqlite_loader.assert_called_once_with(str(fixed_test))
            fixed_test_frame.set_index.assert_called_once_with("index")

    def test_missing_counts_raise_explicit_file_not_found_error(self):
        with tempfile.TemporaryDirectory() as output_dir:
            with self.assertRaisesRegex(
                    FileNotFoundError,
                    "dataset_total_labels_count.*dataset_total_FixedTest_labels_count") as raised:
                self.load_dataset_count(output_dir)

        self.assertIn(output_dir, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
