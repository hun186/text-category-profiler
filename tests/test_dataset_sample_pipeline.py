import unittest

from DatasetConverter.sample_pipeline import aggregate_multi_label_counts
from DatasetConverter.sample_pipeline import assemble_sample_row
from DatasetConverter.sample_pipeline import collect_reader_results
from DatasetConverter.sample_pipeline import collect_source_metadata
from DatasetConverter.sample_pipeline import detect_special_output_label
from DatasetConverter.sample_pipeline import normalize_segment_layout
from DatasetConverter.sample_pipeline import select_rule_based_input_label
from DatasetConverter.sample_schema import validate_sample_rows


class NormalizeSegmentLayoutTests(unittest.TestCase):
    def test_replaces_newlines_above_the_legacy_ten_percent_threshold(self):
        self.assertEqual(
            normalize_segment_layout("abcd\nefgh\n"),
            "abcd efgh ",
        )

    def test_preserves_newlines_at_exactly_the_threshold(self):
        self.assertEqual(
            normalize_segment_layout("123456789\n"),
            "123456789\n",
        )

    def test_preserves_empty_and_single_line_segments(self):
        self.assertEqual(normalize_segment_layout(""), "")
        self.assertEqual(normalize_segment_layout("single line"), "single line")


class DetectSpecialOutputLabelTests(unittest.TestCase):
    def test_labels_segments_with_more_than_ninety_percent_digits(self):
        self.assertEqual(
            detect_special_output_label("1" * 55 + "abcdef"),
            "Uncertainty-Unidentified Digits",
        )

    def test_labels_periods_before_the_repeated_character_fallback(self):
        self.assertEqual(
            detect_special_output_label("." * 56 + "中文文本五"),
            "BD-Table Of Contents",
        )

    def test_labels_dominant_repeated_character_segments(self):
        self.assertEqual(
            detect_special_output_label("~" * 56 + "中文文本五"),
            "False Decoding-Broken Data Stream",
        )

    def test_preserves_strict_threshold_and_residual_text_gate(self):
        self.assertIsNone(detect_special_output_label("1" * 54 + "中文文本六字"))
        self.assertIsNone(detect_special_output_label("." * 401 + "中" * 40))

    def test_returns_none_for_empty_or_regular_text(self):
        self.assertIsNone(detect_special_output_label(""))
        self.assertIsNone(detect_special_output_label("ordinary sample text"))

    def test_preserves_legacy_all_spaces_failure(self):
        with self.assertRaises(ZeroDivisionError):
            detect_special_output_label(" " * 51)


class SelectRuleBasedInputLabelTests(unittest.TestCase):
    def test_selects_highest_info_score_with_inclusive_intervals(self):
        calls = []
        counts = {"first": 1, "second": 3, "outside": 4}

        def match_counter(pattern, text):
            calls.append((pattern, text))
            return counts[pattern]

        selected = select_rule_based_input_label(
            "MIXED Text",
            default_label="original",
            rules={
                ("first", (1, 1)): "low-score",
                ("second", (2, 3)): "high-score",
                ("outside", (0, 3)): "excluded",
            },
            info_scores={"low-score": 1.0, "high-score": 2.0},
            match_counter=match_counter,
        )

        self.assertEqual(selected, "high-score")
        self.assertEqual(
            calls,
            [
                ("first", "mixed text"),
                ("second", "mixed text"),
                ("outside", "mixed text"),
            ],
        )

    def test_returns_default_when_no_rule_matches(self):
        self.assertEqual(
            select_rule_based_input_label(
                "plain text",
                default_label="original",
                rules={("missing", (1, 2)): "override"},
                info_scores={"override": 1.0},
            ),
            "original",
        )

    def test_later_rule_wins_when_info_scores_are_equal(self):
        selected = select_rule_based_input_label(
            "alpha beta",
            default_label="original",
            rules={
                ("alpha", (1, 1)): "first-label",
                ("beta", (1, 1)): "second-label",
            },
            info_scores={"first-label": 5, "second-label": 5},
        )

        self.assertEqual(selected, "second-label")


class AssembleSampleRowTests(unittest.TestCase):
    def test_builds_the_canonical_sliced_text_row(self):
        row = assemble_sample_row(
            file_path="root/#T#[alpha]/article.txt",
            input_label="alpha",
            output_label="mapped-alpha",
            text="sample text",
            part_number=3,
        )

        self.assertEqual(
            row,
            {
                "file": "root/#T#[alpha]/article.txt",
                "InLabel": "alpha",
                "OutLabel": "mapped-alpha",
                "text": "sample text",
                "PartNO": 3,
            },
        )
        self.assertEqual(
            validate_sample_rows([row], source_stage="regular reader"),
            (row,),
        )

    def test_returns_a_fresh_row_for_each_segment(self):
        first = assemble_sample_row(
            file_path="a.txt",
            input_label="alpha",
            output_label="alpha",
            text="first",
            part_number=0,
        )
        second = assemble_sample_row(
            file_path="a.txt",
            input_label="alpha",
            output_label="alpha",
            text="second",
            part_number=1,
        )

        first["text"] = "changed"

        self.assertEqual(second["text"], "second")


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
