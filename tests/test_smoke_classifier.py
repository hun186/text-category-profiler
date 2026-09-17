import os
import sqlite3
import tempfile
import unittest
from unittest import mock
from pathlib import Path


class SmokeClassifierTests(unittest.TestCase):
    def test_writes_one_valid_prediction_per_database_row_and_marker(self):
        from tests.smoke import smoke_classifier

        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset = Path(temporary_directory)
            with sqlite3.connect(dataset / "test.sql3") as connection:
                connection.execute("CREATE TABLE sampleSrc (OutLabel TEXT, text TEXT)")
                connection.executemany(
                    "INSERT INTO sampleSrc (OutLabel, text) VALUES (?, ?)",
                    [
                        ("Aloha", "alpha text"),
                        ("Bosh", "beta text"),
                        ("Aloha", "gamma text"),
                    ],
                )
            (dataset / "TopicAnalysis_LabelList.txt").write_text(
                "Aloha\nBosh\n", encoding="utf-8"
            )
            marker = dataset / "classifier.marker"

            with mock.patch.dict(
                os.environ, {"TCP_SMOKE_CLASSIFIER_MARKER": str(marker)}
            ):
                returncode = smoke_classifier.main(
                    ["-BertDataDir", str(dataset), "--future-option", "ignored"]
                )

            self.assertEqual(returncode, 0)
            predictions = (dataset / "test_results.tsv").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertEqual(len(predictions), 3)
            self.assertTrue(set(predictions) <= {"Aloha", "Bosh"})
            self.assertEqual(marker.read_text(encoding="utf-8").count("\n"), 1)

    def test_invalid_row_labels_cycle_through_sorted_metadata_labels(self):
        from tests.smoke import smoke_classifier

        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset = Path(temporary_directory)
            with sqlite3.connect(dataset / "test.sql3") as connection:
                connection.execute("CREATE TABLE sampleSrc (OutLabel TEXT, text TEXT)")
                connection.executemany(
                    "INSERT INTO sampleSrc (OutLabel, text) VALUES (?, ?)",
                    [("unknown", "one"), (None, "two"), ("Aloha", "three")],
                )
            (dataset / "TopicAnalysis_LabelList.txt").write_text(
                "Bosh\nAloha\n", encoding="utf-8"
            )

            smoke_classifier.main(["-BertDataDir", str(dataset)])

            self.assertEqual(
                (dataset / "test_results.tsv").read_text(encoding="utf-8").splitlines(),
                ["Aloha", "Bosh", "Aloha"],
            )


class FullPipelineFixtureTests(unittest.TestCase):
    fixture_root = Path(__file__).parent / "fixtures" / "full_pipeline_smoke"

    def test_fixed_test_documents_match_taxonomy_and_model_metadata(self):
        expected_labels = {"Aloha", "Bosh"}
        using = self.fixture_root / "fixed_test" / "Using"
        actual_directories = {path.name for path in using.iterdir() if path.is_dir()}
        self.assertEqual(actual_directories, {"#T#[Aloha]", "#T#[Bosh]"})

        for label in expected_labels:
            documents = tuple((using / f"#T#[{label}]").glob("*.txt"))
            self.assertTrue(documents, f"missing FixedTest document for {label}")
            for document in documents:
                text = document.read_text(encoding="utf-8")
                self.assertTrue(text.strip())
                self.assertLess(len(text), 180)

        taxonomy = (self.fixture_root / "taxonomy" / "TopicTree_smoke.csv").read_text(
            encoding="utf-8"
        )
        metadata_labels = set(
            (self.fixture_root / "model" / "TopicAnalysis_LabelList.txt")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        canonical_taxonomy = (
            Path(__file__).parents[1] / "ClassesTree" / "data" / "TopicTree_AK4.csv"
        ).read_text(encoding="utf-8")
        for label in expected_labels:
            self.assertIn(label, taxonomy)
            self.assertIn(label, metadata_labels)
            self.assertIn(label, canonical_taxonomy)


if __name__ == "__main__":
    unittest.main()
