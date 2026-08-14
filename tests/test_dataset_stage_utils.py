import hashlib
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from DatasetConverter.core.stage_utils import FileHashJob
from DatasetConverter.core.stage_utils import make_directory
from DatasetConverter.core.stage_utils import random_replace
from DatasetConverter.core.stage_utils import random_sample
from DatasetConverter.core.stage_utils import show_elapsed_time
from DatasetConverter.core.stage_utils import split_list
from DatasetConverter.core.stage_utils import walk_files


class DatasetStageUtilsTests(unittest.TestCase):
    def test_walk_files_preserves_filters_and_normalized_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "nested").mkdir()
            wanted = root / "nested" / "#T#[alpha].TXT"
            wanted.write_text("alpha", encoding="utf-8")
            (root / "nested" / "ignored.csv").write_text("x", encoding="utf-8")

            result = walk_files(
                str(root),
                Extension=["txt"],
                FullPathFNrePat=r"#T#\[alpha\]",
            )

        self.assertEqual(result, [str(wanted).replace("\\", "/")])

    def test_make_directory_accepts_empty_path_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "created"
            make_directory("")
            make_directory(str(target))
            make_directory(str(target))
            self.assertTrue(target.is_dir())

    def test_split_list_returns_exact_balanced_bucket_count(self):
        self.assertEqual(split_list([1, 2, 3, 4, 5], chunks=3), [[1, 2], [3, 4], [5]])
        self.assertEqual(split_list([1], chunks=3), [[1], [], []])
        with self.assertRaises(ValueError):
            split_list([1], chunks=0)

    def test_file_hash_job_respects_algorithm_and_byte_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.txt"
            path.write_bytes(b"abcdef")
            result = FileHashJob(
                [str(path)], hash_algorithm="sha1", byte_limit=3
            ).run()
        self.assertEqual(result[str(path)], hashlib.sha1(b"abc").hexdigest())

    def test_sampling_and_replacement_can_be_seeded(self):
        state = random.getstate()
        try:
            random.seed(7)
            self.assertEqual(random_sample([1, 2, 3], 10), [2, 1, 3])
            random.seed(7)
            self.assertEqual(random_replace("abcd"), "aUcd")
        finally:
            random.setstate(state)

    def test_elapsed_time_preserves_none_and_print_contract(self):
        self.assertIsNone(show_elapsed_time())
        with patch("DatasetConverter.core.stage_utils.time.time", return_value=12.5):
            with patch("builtins.print") as output:
                self.assertEqual(show_elapsed_time(10), 2.5)
        output.assert_called_once_with("Elapsed time · 2.50 seconds")


if __name__ == "__main__":
    unittest.main()
