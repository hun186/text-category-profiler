import sqlite3
import tempfile
import unittest
from pathlib import Path

from DatasetConverter.sources.sample_sources import PreparedDocument
from DatasetConverter.sources.sample_sources import ElasticsearchDocument
from DatasetConverter.sources.sample_sources import fetch_elasticsearch_response
from DatasetConverter.sources.sample_sources import SourceDocument
from DatasetConverter.sources.sample_sources import apply_regular_cleaning_rules
from DatasetConverter.sources.sample_sources import prepare_document_segments
from DatasetConverter.sources.sample_sources import map_elasticsearch_document
from DatasetConverter.sources.sample_sources import read_czj_corpus_document
from DatasetConverter.sources.sample_sources import read_czj_corpus_titles
from DatasetConverter.sources.sample_sources import read_czj_sample_rows
from DatasetConverter.sources.sample_sources import read_regular_text_document


class MapElasticsearchDocumentTests(unittest.TestCase):
    def test_maps_text_subject_target_date_and_scrap_label(self):
        result = map_elasticsearch_document(
            {
                "_source": {
                    "rawInfo": {"content": "fixture text"},
                    "communication": {"subject": "Fixture subject"},
                    "userNames": ["analyst"],
                    "itcDT": "2026-08-13T12:00:00Z",
                }
            },
            include_subject=True,
        )

        self.assertEqual(
            result,
            ElasticsearchDocument(
                document=SourceDocument("fixture text", ("Scrap",)),
                subject="Fixture subject",
                metadata={"itcDT": "2026-08-13T12:00:00Z", "Target": "T"},
            ),
        )

    def test_omits_subject_lookup_and_target_when_modes_are_inactive(self):
        result = map_elasticsearch_document(
            {"_source": {"rawInfo": {"content": "text"}}},
            include_subject=False,
        )

        self.assertEqual(result.subject, None)
        self.assertEqual(result.metadata, {"itcDT": ""})

    def test_preserves_missing_content_for_retry_adapter(self):
        result = map_elasticsearch_document(
            {"_source": {"rawInfo": {}}},
            include_subject=False,
        )

        self.assertIsNone(result.document.text)

    def test_missing_required_source_shape_fails_fast(self):
        with self.assertRaises(KeyError):
            map_elasticsearch_document({}, include_subject=False)
        with self.assertRaises(KeyError):
            map_elasticsearch_document(
                {"_source": {}}, include_subject=False
            )

    def test_subject_mode_requires_communication_container(self):
        with self.assertRaises(KeyError):
            map_elasticsearch_document(
                {"_source": {"rawInfo": {"content": "text"}}},
                include_subject=True,
            )


class FetchElasticsearchResponseTests(unittest.TestCase):
    class Client:
        def __init__(self, response=None, error=None):
            self.response = response
            self.error = error
            self.closed = False

        def get(self):
            if self.error is not None:
                raise self.error
            return self.response

        def close(self):
            self.closed = True

    def test_retries_missing_content_and_closes_every_client(self):
        created = [
            self.Client({"content": None}),
            self.Client({"content": "ready"}),
        ]
        clients = list(created)

        result = fetch_elasticsearch_response(
            attempts=3,
            create_client=lambda: clients.pop(0),
            fetch=lambda client: client.get(),
            content_from_response=lambda response: response["content"],
            on_error=lambda *args: self.fail("missing content is not an exception"),
        )

        self.assertEqual(result, {"content": "ready"})
        self.assertEqual(clients, [])
        self.assertTrue(all(client.closed for client in created))

    def test_reports_exception_then_retries_without_exposing_factory_inputs(self):
        created = []
        errors = []
        responses = [RuntimeError("unavailable"), {"content": "ready"}]

        def create_client():
            item = responses.pop(0)
            client = (
                self.Client(error=item)
                if isinstance(item, Exception)
                else self.Client(response=item)
            )
            created.append(client)
            return client

        result = fetch_elasticsearch_response(
            attempts=2,
            create_client=create_client,
            fetch=lambda client: client.get(),
            content_from_response=lambda response: response["content"],
            on_error=lambda attempt, error: errors.append((attempt, str(error))),
        )

        self.assertEqual(result, {"content": "ready"})
        self.assertEqual(errors, [(0, "unavailable")])
        self.assertTrue(all(client.closed for client in created))

    def test_returns_none_after_bounded_missing_content_attempts(self):
        created = []

        def create_client():
            client = self.Client({"content": None})
            created.append(client)
            return client

        result = fetch_elasticsearch_response(
            attempts=2,
            create_client=create_client,
            fetch=lambda client: client.get(),
            content_from_response=lambda response: response["content"],
            on_error=lambda *args: None,
        )

        self.assertIsNone(result)
        self.assertEqual(len(created), 2)
        self.assertTrue(all(client.closed for client in created))

    def test_rejects_non_positive_attempt_count_before_creating_client(self):
        with self.assertRaisesRegex(ValueError, "at least 1"):
            fetch_elasticsearch_response(
                attempts=0,
                create_client=lambda: self.fail("client must not be created"),
                fetch=lambda client: {},
                content_from_response=lambda response: None,
                on_error=lambda *args: None,
            )


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


class ReadCzjCorpusTitlesTests(unittest.TestCase):
    def test_reads_titles_in_database_row_order(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "corpus.sql3"
            connection = sqlite3.connect(database_path)
            try:
                connection.execute(
                    "CREATE TABLE Corpus (title TEXT, InLabel TEXT, text TEXT)"
                )
                connection.executemany(
                    "INSERT INTO Corpus VALUES (?, ?, ?)",
                    [("second", "b", "B"), ("first", "a", "A")],
                )
                connection.commit()
            finally:
                connection.close()

            result = read_czj_corpus_titles(
                str(database_path), connect=sqlite3.connect
            )

        self.assertEqual(result, ("second", "first"))

    def test_empty_corpus_returns_empty_tuple(self):
        class EmptyCursor:
            def fetchall(self):
                return []

        class Connection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                return EmptyCursor()

            def close(self):
                self.closed = True

        connection = Connection()
        result = read_czj_corpus_titles(
            "empty.sql3", connect=lambda path: connection
        )

        self.assertEqual(result, ())
        self.assertTrue(connection.closed)

    def test_rejects_null_title_after_closing_connection(self):
        class Cursor:
            def fetchall(self):
                return [(None,)]

        class Connection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                return Cursor()

            def close(self):
                self.closed = True

        connection = Connection()
        with self.assertRaisesRegex(ValueError, "row at index 0 is null"):
            read_czj_corpus_titles(
                "null.sql3", connect=lambda path: connection
            )

        self.assertTrue(connection.closed)

    def test_fetch_failure_still_closes_connection(self):
        class Cursor:
            def fetchall(self):
                raise RuntimeError("fetch failed")

        class Connection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                return Cursor()

            def close(self):
                self.closed = True

        connection = Connection()
        with self.assertRaisesRegex(RuntimeError, "fetch failed"):
            read_czj_corpus_titles(
                "broken.sql3", connect=lambda path: connection
            )

        self.assertTrue(connection.closed)


class ReadCzjSampleRowsTests(unittest.TestCase):
    def create_database(self, database_path, rows=()):
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                'CREATE TABLE sampleSrc ('
                '"index" INTEGER, "file" TEXT, "InLabel" TEXT, '
                '"OutLabel" TEXT, "text" TEXT, "PartNO" INTEGER)'
            )
            connection.executemany(
                "INSERT INTO sampleSrc VALUES (?, ?, ?, ?, ?, ?)", rows
            )
            connection.commit()
        finally:
            connection.close()

    def test_reads_canonical_columns_without_pandas_index(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "samples.sql3"
            self.create_database(
                database_path,
                [(99, "first.txt", "news", "news", "first sample", 3)],
            )

            result = read_czj_sample_rows(
                str(database_path), connect=sqlite3.connect
            )

        self.assertEqual(
            result,
            ({
                "file": "first.txt",
                "InLabel": "news",
                "OutLabel": "news",
                "text": "first sample",
                "PartNO": 3,
            },),
        )
        self.assertNotIn("index", result[0])

    def test_empty_database_returns_stable_empty_tuple(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "empty.sql3"
            self.create_database(database_path)

            result = read_czj_sample_rows(
                str(database_path), connect=sqlite3.connect
            )

        self.assertEqual(result, ())

    def test_missing_canonical_column_fails_and_closes_connection(self):
        class TrackingConnection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                raise sqlite3.OperationalError("no such column: PartNO")

            def close(self):
                self.closed = True

        connection = TrackingConnection()
        with self.assertRaisesRegex(sqlite3.OperationalError, "PartNO"):
            read_czj_sample_rows(
                "malformed.sql3", connect=lambda path: connection
            )

        self.assertTrue(connection.closed)

    def test_fetch_failure_still_closes_connection(self):
        class BrokenCursor:
            description = (
                ("file",), ("InLabel",), ("OutLabel",), ("text",), ("PartNO",)
            )

            def fetchall(self):
                raise RuntimeError("fetch failed")

        class TrackingConnection:
            def __init__(self):
                self.closed = False

            def execute(self, query):
                return BrokenCursor()

            def close(self):
                self.closed = True

        connection = TrackingConnection()
        with self.assertRaisesRegex(RuntimeError, "fetch failed"):
            read_czj_sample_rows("broken.sql3", connect=lambda path: connection)

        self.assertTrue(connection.closed)


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
