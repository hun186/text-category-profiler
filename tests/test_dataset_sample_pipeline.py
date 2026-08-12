import unittest

from DatasetConverter.sample_pipeline import aggregate_multi_label_counts
from DatasetConverter.sample_pipeline import collect_reader_results
from DatasetConverter.sample_pipeline import collect_source_metadata
from DatasetConverter.sample_schema import validate_sample_rows


class CollectReaderResultsTests(unittest.TestCase):
    def test_collects_rows_in_worker_result_order(self):
        first = {"file": "a.txt", "OutLabel": "alpha", "text": "one"}
        second = {"file": "b.txt", "OutLabel": "beta", "text": "two"}

        collected = collect_reader_results(
            [([first], ({"alpha"}, 1)), ([second], None)]
        )

        self.assertEqual(collected.rows, (first, second))
        self.assertEqual(
            collected.multi_label_counts, (({"alpha"}, 1), None)
        )

    def test_empty_results_keep_the_sample_boundary_empty(self):
        collected = collect_reader_results([])

        self.assertEqual(collected.rows, ())
        self.assertEqual(collected.multi_label_counts, ())

    def test_rejects_reader_result_with_missing_contract_member(self):
        with self.assertRaisesRegex(ValueError, "index 0.*rows.*multi-label"):
            collect_reader_results([([], )])

    def test_rejects_non_sequence_rows(self):
        with self.assertRaisesRegex(TypeError, "reader rows at index 0"):
            collect_reader_results([({"file": "a.txt"}, None)])


class ValidateSampleRowsTests(unittest.TestCase):
    def test_preserves_standard_and_external_rows(self):
        standard = {
            "file": "a.txt",
            "InLabel": "alpha",
            "OutLabel": "alpha",
            "text": "one",
            "PartNO": 1,
        }
        external_without_part_number = {
            "file": "es-id",
            "InLabel": "Scrap",
            "OutLabel": "Scrap",
            "text": "two",
        }

        validated = validate_sample_rows(
            [standard, external_without_part_number],
            source_stage="fixed test reader",
        )

        self.assertEqual(validated, (standard, external_without_part_number))

    def test_rejects_non_mapping_with_stage_and_row_index(self):
        with self.assertRaisesRegex(TypeError, "regular reader row at index 0"):
            validate_sample_rows(["not-a-row"], source_stage="regular reader")

    def test_reports_all_missing_required_columns(self):
        with self.assertRaisesRegex(
            ValueError,
            "fixed test reader row at index 0.*InLabel, OutLabel, text",
        ):
            validate_sample_rows(
                [{"file": "fixed.txt"}],
                source_stage="fixed test reader",
            )


class AggregateMultiLabelCountsTests(unittest.TestCase):
    def test_combines_equivalent_label_sets_from_multiple_readers(self):
        counts = aggregate_multi_label_counts(
            [({"beta", "alpha"}, 2), ({"alpha", "beta"}, 3), None]
        )

        self.assertEqual(counts, {("alpha", "beta"): 5})

    def test_ignores_legacy_result_with_no_label_set(self):
        self.assertEqual(aggregate_multi_label_counts([(None, 9)]), {})

    def test_rejects_malformed_reader_counter_with_its_index(self):
        with self.assertRaisesRegex(ValueError, "index 1.*labels.*count"):
            aggregate_multi_label_counts([({"alpha"}, 1), ({"beta"},)])


class CollectSourceMetadataTests(unittest.TestCase):
    def test_preserves_books_and_regular_resolver_results_in_row_order(self):
        calls = []

        def resolver(path, labels):
            calls.append((path, labels))
            if "Books" in path:
                return "Book Type", "Publisher"
            return "Web", "News"

        metadata = collect_source_metadata(
            [
                r"root\Books\#T#[alpha]\publisher\book.txt",
                "root/web/#T#[beta]/news.txt",
            ],
            labels=["alpha", "beta"],
            resolver=resolver,
        )

        self.assertEqual(
            [(item.source_type, item.source) for item in metadata],
            [("Book Type", "Publisher"), ("Web", "News")],
        )
        self.assertEqual(calls[0][1], ["alpha", "beta"])

    def test_preserves_unresolved_path_as_empty_metadata(self):
        metadata = collect_source_metadata(
            ["root/no-label.txt"],
            labels=["alpha"],
            resolver=lambda path, labels: (None, None),
        )

        self.assertIsNone(metadata[0].source_type)
        self.assertIsNone(metadata[0].source)

    def test_rejects_malformed_resolver_result(self):
        with self.assertRaisesRegex(ValueError, "row 0.*source type.*source"):
            collect_source_metadata(
                ["root/file.txt"],
                labels=["alpha"],
                resolver=lambda path, labels: ("only-one-value",),
            )


if __name__ == "__main__":
    unittest.main()
