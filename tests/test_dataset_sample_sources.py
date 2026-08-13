import sqlite3
import tempfile
import unittest
from pathlib import Path

from DatasetConverter.sample_sources import PreparedDocument
from DatasetConverter.sample_sources import SourceDocument
from DatasetConverter.sample_sources import apply_regular_cleaning_rules
from DatasetConverter.sample_sources import prepare_document_segments
from DatasetConverter.sample_sources import read_czj_corpus_document
from DatasetConverter.sample_sources import read_regular_text_document


class ReadRegularTextDocumentTests(unittest.TestCase):
    def test_loads_labels_and_utf8_text_through_injected_adapters(self):
        calls = []

        def labels_from_path(path, **kwargs):
            calls.append(("labels", path, kwargs))
            return ["alpha", "beta"]

        def read_text(**kwargs):
            calls.append(("read", kwargs))
            return "fixture text"

        result = read_regular_text_document(
            "root/#T#[alpha]/sample.TXT",
            unique_sorted_labels=False,
            only_letters_digits_labels=True,
            labels_from_path=labels_from_path,
            read_text=read_text,
        )

        self.assertEqual(
            result,
            SourceDocument("fixture text", ("alpha", "beta")),
        )
        self.assertEqual(
            calls,
            [
                (
                    "labels",
                    "root/#T#[alpha]/sample.TXT",
                    {"UniqueSorted": False, "OnlyLettersDigits": True},
                ),
                (
                    "read",
                    {
                        "file": "root/#T#[alpha]/sample.TXT",
                        "encoding": "utf-8",
                    },
                ),
            ],
        )

    def test_ignores_unlabelled_txt_without_reading_it(self):
        result = read_regular_text_document(
            "unlabelled.txt",
            unique_sorted_labels=True,
            only_letters_digits_labels=False,
            labels_from_path=lambda *args, **kwargs: [],
            read_text=lambda **kwargs: self.fail("unlabelled txt must not be read"),
        )

        self.assertIsNone(result)

    def test_assigns_scrap_to_unlabelled_ai2_before_reading(self):
        result = read_regular_text_document(
            "unlabelled.AI2",
            unique_sorted_labels=True,
            only_letters_digits_labels=False,
            labels_from_path=lambda *args, **kwargs: [],
            read_text=lambda **kwargs: "ai2 text",
        )

        self.assertEqual(result, SourceDocument("ai2 text", ("Scrap",)))

    def test_rejects_non_regular_extension_before_calling_adapters(self):
        with self.assertRaisesRegex(ValueError, r"\.txt or \.ai2"):
            read_regular_text_document(
                "samples.sql3",
                unique_sorted_labels=True,
                only_letters_digits_labels=False,
                labels_from_path=lambda *args, **kwargs: self.fail(
                    "unexpected label adapter call"
                ),
                read_text=lambda **kwargs: self.fail("unexpected reader call"),
            )


class ReadCzjCorpusDocumentTests(unittest.TestCase):
    class FakeCursor:
        def __init__(self, row=None, error=None):
            self.row = row
            self.error = error

        def fetchone(self):
            if self.error is not None:
                raise self.error
            return self.row

    class FakeConnection:
        def __init__(self, row=None, error=None):
            self.cursor = ReadCzjCorpusDocumentTests.FakeCursor(row, error)
            self.calls = []
            self.closed = False

        def execute(self, query, parameters):
            self.calls.append((query, parameters))
            return self.cursor

        def close(self):
            self.closed = True

    def test_loads_named_row_with_parameterized_query_and_closes_connection(self):
        connection = self.FakeConnection(("news", "corpus text"))
        connect_calls = []

        result = read_czj_corpus_document(
            "corpus.sql3",
            title="A title",
            connect=lambda path: connect_calls.append(path) or connection,
        )

        self.assertEqual(result, SourceDocument("corpus text", ("news",)))
        self.assertEqual(connect_calls, ["corpus.sql3"])
        self.assertEqual(
            connection.calls,
            [("SELECT InLabel,text FROM Corpus WHERE title=?", ["A title"])],
        )
        self.assertTrue(connection.closed)

    def test_replaces_null_label_with_scrap(self):
        connection = self.FakeConnection((None, "corpus text"))

        result = read_czj_corpus_document(
            "corpus.sql3",
            title="A title",
            connect=lambda path: connection,
        )

        self.assertEqual(result.input_labels, ("Scrap",))
        self.assertTrue(connection.closed)

    def test_missing_title_raises_diagnostic_after_closing_connection(self):
        connection = self.FakeConnection(None)

        with self.assertRaisesRegex(
            LookupError, r"CZJ corpus title 'missing'.*'corpus.sql3'"
        ):
            read_czj_corpus_document(
                "corpus.sql3",
                title="missing",
                connect=lambda path: connection,
            )

        self.assertTrue(connection.closed)

    def test_fetch_failure_still_closes_connection(self):
        connection = self.FakeConnection(error=RuntimeError("fetch failed"))

        with self.assertRaisesRegex(RuntimeError, "fetch failed"):
            read_czj_corpus_document(
                "corpus.sql3",
                title="A title",
                connect=lambda path: connection,
            )

        self.assertTrue(connection.closed)

    def test_rejects_malformed_row_after_closing_connection(self):
        connection = self.FakeConnection(("label-only",))

        with self.assertRaisesRegex(ValueError, "InLabel/text pair"):
            read_czj_corpus_document(
                "corpus.sql3",
                title="A title",
                connect=lambda path: connection,
            )

        self.assertTrue(connection.closed)

    def test_reads_isolated_sqlite_fixture(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "corpus.sql3"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    "CREATE TABLE Corpus (title TEXT, InLabel TEXT, text TEXT)"
                )
                connection.execute(
                    "INSERT INTO Corpus VALUES (?, ?, ?)",
                    ("Fixture title", "fixture-label", "fixture text"),
                )
                connection.commit()
            finally:
                connection.close()

            result = read_czj_corpus_document(
                str(database_path),
                title="Fixture title",
                connect=sqlite3.connect,
            )

        self.assertEqual(
            result,
            SourceDocument("fixture text", ("fixture-label",)),
        )


class ApplyRegularCleaningRulesTests(unittest.TestCase):
    def test_accumulates_and_applies_eligible_rules_in_mapping_order(self):
        calls = []
        rules = {
            "first": {"pattern": "a"},
            "second": {"pattern": "b"},
        }

        def clean_text(text, active_rules):
            calls.append((text, tuple(active_rules)))
            return f"{text}:{tuple(active_rules)[-1]}"

        result = apply_regular_cleaning_rules(
            SourceDocument("start", ("news",)),
            rules=rules,
            labels_in_exemptions=lambda labels, exemptions: [],
            clean_text=clean_text,
        )

        self.assertEqual(result, SourceDocument("start:first:second", ("news",)))
        self.assertEqual(
            calls,
            [
                ("start", ("first",)),
                ("start:first", ("first", "second")),
            ],
        )

    def test_skips_rules_when_document_labels_overlap_exemptions(self):
        overlap_calls = []
        cleaner_calls = []
        rules = {
            "skip": {"ExemptInLabelList": ["news"]},
            "apply": {"ExemptInLabelList": ["sports"]},
        }

        def labels_in_exemptions(labels, exemptions):
            overlap_calls.append((tuple(labels), tuple(exemptions)))
            return sorted(set(labels).intersection(exemptions))

        def clean_text(text, active_rules):
            cleaner_calls.append(tuple(active_rules))
            return "cleaned"

        result = apply_regular_cleaning_rules(
            SourceDocument("start", ("news",)),
            rules=rules,
            labels_in_exemptions=labels_in_exemptions,
            clean_text=clean_text,
        )

        self.assertEqual(result, SourceDocument("cleaned", ("news",)))
        self.assertEqual(
            overlap_calls,
            [(('news',), ('news',)), (('news',), ('sports',))],
        )
        self.assertEqual(cleaner_calls, [("apply",)])

    def test_empty_rules_do_not_call_adapters_or_change_document(self):
        document = SourceDocument("unchanged", ("news",))

        result = apply_regular_cleaning_rules(
            document,
            rules={},
            labels_in_exemptions=lambda *args: self.fail("unexpected overlap call"),
            clean_text=lambda *args: self.fail("unexpected cleaner call"),
        )

        self.assertEqual(result, document)


class PrepareDocumentSegmentsTests(unittest.TestCase):
    def test_normalizes_before_dividing_and_returns_named_immutable_result(self):
        calls = []

        def normalize_text(text):
            calls.append(("normalize", text))
            return "normalized text"

        def divide_text(text):
            calls.append(("divide", text))
            return ["first", "second"]

        result = prepare_document_segments(
            SourceDocument("raw text", ("news", "analysis")),
            normalize_text=normalize_text,
            divide_text=divide_text,
        )

        self.assertEqual(
            result,
            PreparedDocument(
                text="normalized text",
                input_labels=("news", "analysis"),
                segments=("first", "second"),
            ),
        )
        self.assertEqual(
            calls,
            [("normalize", "raw text"), ("divide", "normalized text")],
        )

    def test_preserves_empty_segment_sequence_without_extra_adapter_calls(self):
        result = prepare_document_segments(
            SourceDocument("raw", ("news",)),
            normalize_text=lambda text: text,
            divide_text=lambda text: [],
        )

        self.assertEqual(result.segments, ())
        self.assertEqual(result.input_labels, ("news",))


if __name__ == "__main__":
    unittest.main()
