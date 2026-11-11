"""BL-001: fixed legacy SQLite writer has one source and closes connections.

Uses isolated AST for stage wrappers and in-memory stubs. The optional pandas
integration test uses *private in-memory* SQLite, never real WorkPool files.
"""
import ast
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

from text_category_profiler.data.stage_sql import write_stage_sql


ROOT = Path(__file__).resolve().parents[1]
STAGES = ("DatasetConverter/df_utils.py", "BertScript/df_utils.py")


def isolated_stage_writer(path, **injections):
    source = (ROOT / path).read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    methods = [node for node in tree.body
               if isinstance(node, ast.FunctionDef) and node.name == "dfToSQL"]
    if len(methods) != 1:
        raise AssertionError("Expected exactly one stage dfToSQL: " + path)
    namespace = dict(injections)
    exec(compile(ast.Module(body=methods, type_ignores=[]), path, "exec"),
         namespace)
    return namespace["dfToSQL"], methods[0]


class FakeConnection:
    def __init__(self, events, fail_index=False):
        self.events = events
        self.fail_index = fail_index

    def execute(self, sql):
        self.events.append(("execute", sql))
        if self.fail_index:
            raise LookupError("injected index creation error")

    def close(self):
        self.events.append(("close",))


class FakeDataFrame:
    class Cols:
        values = ["text", "label"]

    def __init__(self, events, fail_select=False, fail_sql=False):
        self.columns = self.Cols()
        self.loc = self
        self.events = events
        self.fail_select = fail_select
        self.fail_sql = fail_sql

    def __getitem__(self, query):
        self.events.append(("select", query[1]))
        if self.fail_select:
            raise LookupError("injected column selection error")
        return self

    def to_sql(self, **kwargs):
        self.events.append(("to_sql", kwargs))
        if self.fail_sql:
            raise RuntimeError("injected SQL writer error")


class ConnectionFactory:
    def __init__(self, events, fail_index=False):
        self.events = events
        self.conn = FakeConnection(events, fail_index)

    def connect(self, name):
        self.events.append(("connect", name))
        return self.conn


class StageSQLiteTests(unittest.TestCase):
    def test_both_stage_apis_are_explicit_delegates(self):
        for path in STAGES:
            with self.subTest(stage=path):
                fn, node = isolated_stage_writer(path)
                imports = [
                    x for x in ast.walk(node)
                    if isinstance(x, ast.ImportFrom) and
                    x.module == "text_category_profiler.data.stage_sql"
                ]
                self.assertEqual(len(imports), 1)
                self.assertEqual([n.name for n in imports[0].names],
                                 ["write_stage_sql"])
                self.assertFalse(any(
                    isinstance(x, ast.Call)
                    and isinstance(x.func, ast.Attribute)
                    and x.func.attr in ("to_sql", "execute", "close")
                    for x in ast.walk(node)
                ))

    def test_fixed_table_index_and_default_columns_preserved_with_close(self):
        for path in STAGES:
            with self.subTest(stage=path):
                events = []
                db = ConnectionFactory(events)
                frame = FakeDataFrame(events)
                fn, _ = isolated_stage_writer(path, lite=db)
                self.assertIsNone(fn("out.sql3", frame))
                self.assertEqual(events, [
                    ("connect", "out.sql3"),
                    ("select", ["text", "label"]),
                    ("to_sql", {"name": "sampleSrc", "con": db.conn,
                                "if_exists": "replace"}),
                    ("execute", 'CREATE INDEX "text_Index" ON "sampleSrc"("text");'),
                    ("close",),
                ])
                with self.assertRaises(TypeError):
                    fn("out.sql3", frame, table="other")

    def test_explicit_saved_columns_are_preserved(self):
        events = []
        db = ConnectionFactory(events)
        fn, _ = isolated_stage_writer(STAGES[0], lite=db)
        self.assertIsNone(fn("out.sql3", FakeDataFrame(events), ["text"]))
        self.assertEqual(events[1], ("select", ["text"]))
        self.assertEqual(events[-1], ("close",))

    def test_column_sql_and_index_failures_close_exactly_once(self):
        for condition in ("select", "sql", "index"):
            with self.subTest(condition=condition):
                events = []
                db = ConnectionFactory(events, fail_index=(condition == "index"))
                frame = FakeDataFrame(
                    events, fail_select=condition == "select",
                    fail_sql=condition == "sql",
                )
                fn, _ = isolated_stage_writer(STAGES[1], lite=db)
                with self.assertRaises((LookupError, RuntimeError)):
                    fn("failure.sql3", frame)
                self.assertEqual(events.count(("close",)), 1)
                self.assertEqual(events[-1], ("close",))

    def test_missing_text_preflight_rejects_before_connection_or_writes(self):
        class LabelOnlyFrame(FakeDataFrame):
            class Cols:
                values = ["label"]

        for stage in STAGES:
            with self.subTest(stage=stage):
                events = []
                db = ConnectionFactory(events)
                fn, _ = isolated_stage_writer(stage, lite=db)
                with self.assertRaisesRegex(ValueError, "requires a 'text' column"):
                    fn("existing.sql3", LabelOnlyFrame(events))
                self.assertEqual(events, [], "Must not connect or replace a table")

                # Even if the input has text, selecting only the label
                # would create sampleSrc *without* text after replace.
                with self.assertRaisesRegex(ValueError, "requires a 'text' column"):
                    fn("existing.sql3", FakeDataFrame(events), ["label"])
                self.assertEqual(events, [])

    def test_private_disk_sqlite_reopen_replace_and_unsafe_input_preservation(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Optional pandas integration not available")

        class Tracked(sqlite3.Connection):
            def close(self):
                self.was_closed = True
                super().close()

        with tempfile.TemporaryDirectory(prefix="bl001-stage-sql-") as temp:
            for stage in STAGES:
                with self.subTest(stage=stage):
                    path = Path(temp) / (stage.split("/")[0] + ".sqlite3")
                    connections = []

                    def connect(filename):
                        result = sqlite3.connect(filename, factory=Tracked)
                        connections.append(result)
                        return result

                    class DB:
                        pass

                    db = DB()
                    db.connect = connect
                    fn, _ = isolated_stage_writer(stage, lite=db)
                    first = pd.DataFrame({
                        "text": ["舊資料", "測試"],
                        "label": ["TW Affairs", "TW Security"],
                    })
                    latest = pd.DataFrame({
                        "text": ["新資料"], "label": ["TW Local"],
                    })
                    self.assertIsNone(fn(str(path), first))
                    self.assertIsNone(fn(str(path), latest))
                    self.assertEqual(len(connections), 2)
                    for connection in connections:
                        self.assertTrue(connection.was_closed)
                        with self.assertRaises(sqlite3.ProgrammingError):
                            connection.execute("SELECT 1")

                    # A fresh connection proves persisted replace semantics,
                    # and a real index bound to "text" rather than an
                    # SQLite double-quoted string expression.
                    with sqlite3.connect(path) as reopened:
                        rows = reopened.execute(
                            'SELECT "text", "label" FROM "sampleSrc"'
                        ).fetchall()
                        self.assertEqual(rows, [("新資料", "TW Local")])
                        index_columns = [
                            row[2] for row in reopened.execute(
                                'PRAGMA index_info("text_Index")'
                            ).fetchall()
                        ]
                        self.assertEqual(index_columns, ["text"])

                    original_bytes = path.read_bytes()
                    invalid = pd.DataFrame({"label": ["意外覆蓋"]})
                    with self.assertRaisesRegex(ValueError, "requires a 'text' column"):
                        fn(str(path), invalid)
                    with self.assertRaisesRegex(ValueError, "requires a 'text' column"):
                        fn(str(path), latest, ["label"])
                    self.assertEqual(len(connections), 2, "Invalid calls must not connect")
                    self.assertEqual(path.read_bytes(), original_bytes)

    def test_shared_sql_module_does_not_import_models_pandas_or_backends(self):
        source = (ROOT / "text_category_profiler/data/stage_sql.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        self.assertFalse(any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            for node in tree.body
        ))

    def test_real_private_memory_sqlite_retains_unicode_rows_and_text_index(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Optional pandas integration not available")

        class Tracked(sqlite3.Connection):
            def close(self):
                self.was_closed = True
                super().close()

        original_connect = sqlite3.connect
        for stage in STAGES:
            with self.subTest(stage=stage):
                uri = "file:bl001_sql_" + uuid.uuid4().hex + "?mode=memory&cache=shared"
                anchor = original_connect(uri, uri=True)
                connections = []

                def connect(_):
                    connection = original_connect(
                        uri, uri=True, factory=Tracked,
                    )
                    connections.append(connection)
                    return connection

                # Isolated stage AST binds sqlite3's connect via the stage alias.
                class DB:
                    pass
                db = DB()
                db.connect = connect
                frame = pd.DataFrame({"text": ["台北", "桃園"],
                                      "label": ["TW Affairs", "TW Security"]})
                try:
                    fn, _ = isolated_stage_writer(stage, lite=db)
                    self.assertIsNone(fn("only-memory", frame))
                    self.assertEqual(len(connections), 1)
                    self.assertTrue(connections[0].was_closed)
                    with self.assertRaises(sqlite3.ProgrammingError):
                        connections[0].execute("SELECT 1")
                    rows = anchor.execute(
                        'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
                    ).fetchall()
                    self.assertEqual(rows, [
                        ("台北", "TW Affairs"), ("桃園", "TW Security"),
                    ])
                    indexes = {
                        row[0] for row in anchor.execute(
                            "SELECT name FROM sqlite_master WHERE type='index'"
                        )
                    }
                    self.assertIn("text_Index", indexes)
                finally:
                    anchor.close()


if __name__ == "__main__":
    unittest.main()
