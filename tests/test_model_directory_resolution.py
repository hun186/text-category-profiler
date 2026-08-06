import os
import tempfile
import unittest
from pathlib import Path

from PythonModule.utils.model_paths import resolve_local_model_directory


class ModelDirectoryResolutionTests(unittest.TestCase):
    def test_finds_bare_model_name_under_bertscript(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            repository = Path(temporary_directory)
            model_directory = repository / "BertScript" / "mmBERT-base"
            model_directory.mkdir(parents=True)

            previous_directory = os.getcwd()
            try:
                os.chdir(repository)
                resolved = resolve_local_model_directory("mmBERT-base")
            finally:
                os.chdir(previous_directory)

            self.assertEqual(resolved, os.path.join("BertScript", "mmBERT-base"))

    def test_preserves_an_explicit_existing_model_path(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            model_directory = Path(temporary_directory) / "custom-model"
            model_directory.mkdir()

            resolved = resolve_local_model_directory(str(model_directory))

            self.assertEqual(resolved, str(model_directory))

    def test_returns_none_when_no_local_directory_exists(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            previous_directory = os.getcwd()
            try:
                os.chdir(temporary_directory)
                resolved = resolve_local_model_directory("missing-model")
            finally:
                os.chdir(previous_directory)

            self.assertIsNone(resolved)


if __name__ == "__main__":
    unittest.main()
