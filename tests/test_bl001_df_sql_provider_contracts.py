"""BL-001 no-service characterization of three dfToSQL writer contracts.

Only dfToSQL ASTs execute against fake DataFrames and SQLite connections.
No pandas, SQL database, model, Elasticsearch, filesystem or WorkPool I/O.
"""
import ast
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ("DatasetConverter/df_utils.py", "BertScript/df_utils.py")
CANONICAL = "text_category_profiler/data/df_utils.py"


def isolate_sql_writer(path, **dependencies):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"), filename=path)
    methods = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "dfToSQL"
    ]
    if len(methods) != 1:
        raise AssertionError(f"Expected exactly one dfToSQL in {path}")
    scope = dict(dependencies)
    exec(compile(ast.Module(body=methods, type_ignores=[]), path, "exec"), scope)
    return scope["dfToSQL"]


class RecorderFrame:
    def __init__(self, events, fail=False):
        self.events = events
        self.fail = fail
        self.columns = type("Columns", (), {"values": ["text", "label"]})()
        self.loc = self

    def __getitem__(self, selection):
        self.events.append(("select", selection[1]))
        if not isinstance(selection, tuple) or selection[0] != slice(None):
            raise AssertionError("Unexpected DataFrame selection")
        return self

    def __len__(self):
        return 0  # Keep canonical JSON normalization out of this isolated test.

    def to_sql(self, **kwargs):
        self.events.append(("to_sql", kwargs))
        if self.fail:
            raise RuntimeError("injected SQL export failure")


class RecorderConnection:
    def __init__(self, events):
        self.events = events

    def execute(self, statement):
        self.events.append(("execute", statement))

    def close(self):
        self.events.append(("close",))


class FakeLite:
    def __init__(self, events):
        self.events = events
        self.connection = RecorderConnection(events)

    def connect(self, path):
        self.events.append(("connect", path))
        return self.connection


class SQLProviderContractTests(unittest.TestCase):
    def test_stage_local_writers_share_fixed_replace_and_index_contract(self):
        observed = []
        for path in LEGACY:
            with self.subTest(provider=path):
                events = []
                lite = FakeLite(events)
                frame = RecorderFrame(events)
                fn = isolate_sql_writer(path, lite=lite)
                self.assertIsNone(fn("legacy.sql3", frame))
                self.assertEqual(events, [
                    ("connect", "legacy.sql3"),
                    ("select", ["text", "label"]),
                    ("to_sql", {"name": "sampleSrc", "con": lite.connection, "if_exists": "replace"}),
                    ("execute", 'CREATE INDEX "text_Index" ON "sampleSrc"("text");'),
                ])
                observed.append([item[0] for item in events])
                with self.assertRaises(TypeError):
                    fn("legacy.sql3", frame, table="another")
        self.assertEqual(observed[0], observed[1])
        # Existing legacy functions have no close() call on this path.

    def test_canonical_defaults_use_logger_and_close_connection(self):
        events = []
        lite = FakeLite(events)
        frame = RecorderFrame(events)

        def logger():
            events.append(("logger",))
            return "fake-logger"

        fn = isolate_sql_writer(CANONICAL, lite=lite, MPlogger=logger)
        self.assertIsNone(fn("canonical.sql3", frame))
        self.assertEqual(events, [
            ("logger",),
            ("connect", "canonical.sql3"),
            ("select", ["text", "label"]),
            ("to_sql", {
                "name": "sampleSrc", "con": lite.connection, "if_exists": "replace",
                "dtype": None, "index_label": None,
            }),
            ("close",),
        ])
        self.assertNotIn("execute", [item[0] for item in events])

    def test_canonical_passes_custom_append_table_and_index_contract(self):
        events = []
        lite = FakeLite(events)
        frame = RecorderFrame(events)
        logger = object()
        index_calls = []

        def indexer(*args, **kwargs):
            index_calls.append((args, kwargs))

        fn = isolate_sql_writer(
            CANONICAL, lite=lite, MPlogger=lambda: None, createIndex=indexer,
        )
        fn(
            "append.sql3", frame, SavingDfColumns=["text"],
            IndexCols=["text"], UniqueIndexCols=["document_id"],
            dtype={"text": "TEXT"}, table="records",
            MPLOGGER=logger, if_exists="append", index_label="ignored",
        )
        self.assertEqual(events, [
            ("connect", "append.sql3"),
            ("select", ["text"]),
            ("to_sql", {
                "name": "records", "con": lite.connection, "if_exists": "append",
                "dtype": {"text": "TEXT"}, "index_label": ["document_id"],
            }),
            ("close",),
        ])
        self.assertEqual(index_calls, [(
            ("append.sql3",),
            {"table": "records", "IndexCol": "text", "connection": lite.connection,
             "MPLOGGER": logger},
        )])

    def test_canonical_export_exception_closes_connection(self):
        events = []
        lite = FakeLite(events)
        frame = RecorderFrame(events, fail=True)
        fn = isolate_sql_writer(CANONICAL, lite=lite, MPlogger=lambda: object())
        with self.assertRaisesRegex(RuntimeError, "injected SQL export failure"):
            fn("failed.sql3", frame)
        self.assertEqual(
            [e[0] for e in events], ["connect", "select", "to_sql", "close"]
        )

    def test_canonical_index_exception_closes_connection(self):
        events = []
        lite = FakeLite(events)
        frame = RecorderFrame(events)

        def broken_index(*args, **kwargs):
            events.append(("create_index",))
            raise LookupError("injected index failure")

        fn = isolate_sql_writer(
            CANONICAL, lite=lite, MPlogger=lambda: object(),
            createIndex=broken_index,
        )
        with self.assertRaisesRegex(LookupError, "injected index failure"):
            fn("failed-index.sql3", frame, IndexCols=["text"])
        self.assertEqual(
            [e[0] for e in events],
            ["connect", "select", "to_sql", "create_index", "close"],
        )

    def test_canonical_dataframe_selection_exception_closes_connection(self):
        events = []
        lite = FakeLite(events)

        class BrokenSelection(RecorderFrame):
            def __getitem__(self, selection):
                self.events.append(("select", selection[1]))
                raise LookupError("injected selection failure")

        fn = isolate_sql_writer(CANONICAL, lite=lite, MPlogger=lambda: object())
        with self.assertRaisesRegex(LookupError, "injected selection failure"):
            fn("failed-selection.sql3", BrokenSelection(events))
        self.assertEqual([e[0] for e in events], ["connect", "select", "close"])


    def test_canonical_structured_cells_are_json_encoded_but_legacy_cells_are_not(self):
        class Names:
            values = ["payload"]

            def __iter__(self):
                return iter(self.values)

        class Series:
            def __init__(self, values):
                self.values = values

            def apply(self, fn):
                return [fn(x) for x in self.values]

        class PayloadFrame:
            def __init__(self, rows):
                self.values = {"payload": list(rows)}
                self.columns = Names()
                self.loc = self
                self.saved = None

            def __getitem__(self, key):
                if isinstance(key, tuple):
                    if key[0] != slice(None) or key[1] != ["payload"]:
                        raise AssertionError("Unexpected selection")
                    return self
                return Series(self.values[key])

            def __setitem__(self, key, values):
                self.values[key] = list(values)

            def __len__(self):
                return len(self.values["payload"])

            def to_sql(self, **kwargs):
                self.saved = list(self.values["payload"])

        rows = [{"name": "中文"}, ["甲", "乙"], ("組", 2), "untouched"]
        expected = [
            json.dumps(rows[0], ensure_ascii=False),
            json.dumps(rows[1], ensure_ascii=False),
            json.dumps(rows[2], ensure_ascii=False),
            "untouched",
        ]
        canonical = PayloadFrame(rows)
        fn = isolate_sql_writer(
            CANONICAL, lite=FakeLite([]), json=json, MPlogger=lambda: object()
        )
        self.assertIsNone(fn("isolated.sql3", canonical))
        self.assertEqual(canonical.saved, expected)
        self.assertEqual(canonical.values["payload"], expected)

        for path in LEGACY:
            with self.subTest(provider=path):
                legacy = PayloadFrame(rows)
                fn = isolate_sql_writer(path, lite=FakeLite([]))
                self.assertIsNone(fn("isolated.sql3", legacy))
                self.assertEqual(legacy.saved, rows)
                self.assertEqual(legacy.values["payload"], rows)
        # No real pandas behavior or SQLite persistence is inferred here.

if __name__ == "__main__":
    unittest.main()
