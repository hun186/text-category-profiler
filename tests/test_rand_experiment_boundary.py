"""Dependency-light characterization of the isolated RAND corpus experiment."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import runpy
import tempfile
import types
import unittest
from unittest import mock

from experiments import rand_corpus_labeling as experiment
from text_category_profiler import utilities_RAND as legacy


ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments" / "rand_corpus_labeling.py"
LEGACY = ROOT / "text_category_profiler" / "utilities_RAND.py"


class RandExperimentBoundaryTests(unittest.TestCase):
    def test_import_only_has_no_workflow_side_effects(self):
        for file in (EXPERIMENT, LEGACY):
            with self.subTest(file=file), tempfile.TemporaryDirectory() as temp:
                previous = Path.cwd()
                try:
                    os.chdir(temp)
                    with redirect_stdout(io.StringIO()) as output:
                        namespace = runpy.run_path(str(file), run_name="import_check")
                    self.assertEqual(output.getvalue(), "")
                    self.assertEqual(list(Path(temp).iterdir()), [])
                    self.assertIn("main", namespace)
                finally:
                    os.chdir(previous)

    def test_legacy_helper_api_remains_available(self):
        self.assertIs(legacy.LoadTree, experiment.LoadTree)
        self.assertIs(legacy.GetSubNodes, experiment.GetSubNodes)
        self.assertIs(legacy.RANDLoader, experiment.RANDLoader)
        with self.assertRaises(AttributeError):
            getattr(legacy, "unknown_name")

    def test_tree_helpers_and_metadata_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "TopicTree.txt").write_text(
                "Root,Child,20261028\nChild,Leaf,20261028\ninvalid\n",
                encoding="utf-8")
            self.assertEqual(experiment.LoadTree(root / "TopicTree.txt"),
                             [["Root", "Child"], ["Child", "Leaf"]])
            self.assertEqual(experiment.GetSubNodes(
                [["Root", "Child"], ["Child", "Leaf"]], ["Root"]), ["Child"])
            loader = experiment.RANDLoader(str(root))
            self.assertEqual(loader.RANDMetadataFile, str(root / "RAND_Metadata.sql3"))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(loader.GetSubtopics(["Root"]), ["Root", "Child", "Leaf"])

    def test_metadata_data_dependency_only_loaded_when_requested(self):
        fake = types.ModuleType("text_category_profiler.data.df_utils")
        loader = mock.Mock(return_value="sentinel")
        fake.dfFromSQLite3 = loader
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.dict("sys.modules", {"text_category_profiler.data.df_utils": fake}):
                self.assertEqual(experiment.RANDLoader(temp).GetMetadata(), "sentinel")
            loader.assert_called_once_with(
                str(Path(temp) / "RAND_Metadata.sql3"),
                columnList=["title", "topics", "FilePath"])

    def test_legacy_main_only_delegates_explicit_execution(self):
        cwd = Path.cwd()
        with mock.patch("runpy.run_path") as dispatcher:
            legacy.main()
        dispatcher.assert_called_once_with(str(EXPERIMENT), run_name="__main__")
        self.assertEqual(Path.cwd(), cwd)


if __name__ == "__main__":
    unittest.main()
