import unittest

from DatasetConverter.core.sample_pipeline import aggregate_multi_label_counts
from DatasetConverter.core.sample_pipeline import assemble_sample_row
from DatasetConverter.core.sample_pipeline import build_elasticsearch_provenance
from DatasetConverter.core.sample_pipeline import collect_reader_results
from DatasetConverter.core.sample_pipeline import collect_source_metadata
from DatasetConverter.core.sample_pipeline import detect_special_output_label
from DatasetConverter.core.sample_pipeline import normalize_segment_layout
from DatasetConverter.core.sample_pipeline import prepare_sample_text
from DatasetConverter.core.sample_pipeline import select_document_samples
from DatasetConverter.core.sample_pipeline import select_rule_based_input_label
from DatasetConverter.core.sample_pipeline import transform_sample_segment
from DatasetConverter.core.sample_schema import validate_sample_rows


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


class BuildElasticsearchProvenanceTests(unittest.TestCase):
    def test_builds_subject_target_and_date_in_legacy_order(self):
        sanitized_subjects = []

        def sanitize(subject):
            sanitized_subjects.append(subject)
            return "clean-subject"

        result = build_elasticsearch_provenance(
            "42",
            es_job={"Vis_ESFileNameMode": "subject_id", "es_tokens": ["token"]},
            metadata={"Target": "T", "itcDT": "2026-08-13T09:10:11"},
            subject=123,
            sanitize_filename=sanitize,
        )

        self.assertEqual(sanitized_subjects, ["123"])
        self.assertEqual(result.file_path, "20260813/Target/clean-subject_42")
        self.assertIsNone(result.invalid_date)

    def test_supports_fractional_and_zulu_legacy_date_formats(self):
        for source_date in (
            "2026-08-13T09:10:11.123456Z",
            "2026-08-13T09:10:11Z",
        ):
            with self.subTest(source_date=source_date):
                result = build_elasticsearch_provenance(
                    "42",
                    es_job={},
                    metadata={"itcDT": source_date},
                    subject=None,
                    sanitize_filename=lambda value: value,
                )
                self.assertEqual(result.file_path, "20260813/42")
                self.assertIsNone(result.invalid_date)

    def test_preserves_non_target_and_invalid_date_fallback(self):
        result = build_elasticsearch_provenance(
            "42",
            es_job={"es_tokens": []},
            metadata={"Target": "unexpected", "itcDT": "not-a-date"},
            subject=None,
            sanitize_filename=lambda value: value,
        )

        self.assertEqual(result.file_path, "None/NonTarget/42")
        self.assertEqual(result.invalid_date, "not-a-date")

    def test_does_not_sanitize_subject_when_subject_mode_is_disabled(self):
        result = build_elasticsearch_provenance(
            "42",
            es_job={},
            metadata={},
            subject="ignored",
            sanitize_filename=lambda value: self.fail("unexpected sanitizer call"),
        )

        self.assertEqual(result.file_path, "42")
        self.assertIsNone(result.invalid_date)

    def test_reports_non_string_date_as_invalid_metadata(self):
        result = build_elasticsearch_provenance(
            "42",
            es_job={},
            metadata={"itcDT": 20260813},
            subject=None,
            sanitize_filename=lambda value: value,
        )

        self.assertEqual(result.file_path, "None/42")
        self.assertEqual(result.invalid_date, 20260813)


class PrepareSampleTextTests(unittest.TestCase):
    def test_converts_before_evaluating_minimum_length(self):
        calls = []

        def convert(text, conversion):
            calls.append((text, conversion))
            return text + "x"

        result = prepare_sample_text(
            "abc",
            minimum_length=4,
            conversion="tw2s",
            convert=convert,
        )

        self.assertEqual(calls, [("abc", "tw2s")])
        self.assertEqual(result, "abcx")

    def test_accepts_text_at_exact_minimum_length(self):
        self.assertEqual(
            prepare_sample_text(
                "abcd",
                minimum_length=4,
                conversion=None,
                convert=lambda text, conversion: self.fail("unexpected conversion"),
            ),
            "abcd",
        )

    def test_rejects_text_below_minimum_length(self):
        self.assertIsNone(
            prepare_sample_text(
                "abc",
                minimum_length=4,
                conversion=None,
                convert=lambda text, conversion: self.fail("unexpected conversion"),
            )
        )


class TransformSampleSegmentTests(unittest.TestCase):
    def test_returns_named_accepted_result_after_all_normal_stages(self):
        result = transform_sample_segment(
            "alpha\ntext",
            file_path="source.txt",
            input_label="original",
            part_number=2,
            rule_based_active=True,
            rules={("alpha", (1, 1)): "matched"},
            info_scores={"matched": 5},
            label_conversion={"matched": "mapped"},
            minimum_length=10,
            text_conversion="tw2s",
            convert=lambda text, conversion: text + "!",
        )

        self.assertEqual(result.reason, "accepted")
        self.assertEqual(
            result.row,
            {
                "file": "source.txt",
                "InLabel": "matched",
                "OutLabel": "mapped",
                "text": "alpha\ntext!",
                "PartNO": 2,
            },
        )

    def test_reports_below_minimum_without_assembling_a_row(self):
        result = transform_sample_segment(
            "short",
            file_path="source.txt",
            input_label="original",
            part_number=0,
            rule_based_active=False,
            rules={},
            info_scores={},
            label_conversion={},
            minimum_length=6,
            text_conversion=None,
            convert=lambda text, conversion: text,
        )

        self.assertIsNone(result.row)
        self.assertEqual(result.reason, "below-minimum-length")

    def test_special_label_bypasses_conversion_length_and_label_mapping(self):
        def unexpected_conversion(text, conversion):
            self.fail("special segment must bypass text conversion")

        result = transform_sample_segment(
            "1" * 55 + "abcdef",
            file_path="source.txt",
            input_label="original",
            part_number=4,
            rule_based_active=True,
            rules={("1", (1, 100)): "matched"},
            info_scores={"matched": 5},
            label_conversion={"original": "mapped"},
            minimum_length=1000,
            text_conversion="tw2s",
            convert=unexpected_conversion,
        )

        self.assertEqual(result.reason, "special-label")
        self.assertEqual(result.row["InLabel"], "original")
        self.assertEqual(result.row["OutLabel"], "Uncertainty-Unidentified Digits")
        self.assertEqual(result.row["PartNO"], 4)

    def test_preserves_missing_label_conversion_failure(self):
        with self.assertRaises(KeyError):
            transform_sample_segment(
                "long enough",
                file_path="source.txt",
                input_label="missing",
                part_number=0,
                rule_based_active=False,
                rules={},
                info_scores={},
                label_conversion={"configured": "mapped"},
                minimum_length=1,
                text_conversion=None,
                convert=lambda text, conversion: text,
            )


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


class SelectDocumentSamplesTests(unittest.TestCase):
    def test_shuffles_before_applying_label_specific_bound(self):
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        calls = []

        def reverse(items):
            calls.append(list(items))
            items.reverse()

        selected = select_document_samples(
            rows,
            input_label="alpha",
            bounds={"default": 3, "alpha": 2},
            random_sample=True,
            shuffle=reverse,
        )

        self.assertEqual(calls, [rows])
        self.assertEqual(selected, [{"id": 3}, {"id": 2}])
        self.assertEqual(rows, [{"id": 1}, {"id": 2}, {"id": 3}])

    def test_uses_default_bound_without_calling_shuffle_when_disabled(self):
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]

        def unexpected_shuffle(items):
            self.fail(f"shuffle should not be called for {items!r}")

        selected = select_document_samples(
            rows,
            input_label="unconfigured",
            bounds={"default": 2},
            random_sample=False,
            shuffle=unexpected_shuffle,
        )

        self.assertEqual(selected, rows[:2])

    def test_preserves_legacy_missing_default_failure(self):
        with self.assertRaises(KeyError):
            select_document_samples(
                [{"id": 1}],
                input_label="unconfigured",
                bounds={},
                random_sample=False,
                shuffle=lambda items: None,
            )


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
