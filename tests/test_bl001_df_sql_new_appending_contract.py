"""Bounded BL-001 exception-cleanup characterization for dfToSQL_new_appending.

Executes only the target function's AST with an in-memory fake SQLite adapter.
No actual DB, pandas, WorkPool, model, ES, or filesystem writes occur.
"""
import ast
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PROVIDER = ROOT / "text_category_profiler" / "data" / "df_utils.py"


def isolated_writer(ensure_schema):
    tree = ast.parse(PROVIDER.read_text(encoding="utf-8-sig"))
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "dfToSQL_new_appending"
    ]
    if len(matches) != 1:
        raise AssertionError("Expected exactly one alternate SQL writer")
    scope = {"ensure_schema": ensure_schema}
    exec(
        compile(ast.Module(body=matches, type_ignores=[]), str(PROVIDER), "exec"),
        scope,
    )
    return scope["dfToSQL_new_appending"]


class FakeCursor:
    """Minimum sqlite3 cursor result contract needed by the writer."""

    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchall(self):
        return list(self.rows)


class FakeConnection:
    def __init__(self, events, fail_index=None):
        self.events = events
        self.fail_index = fail_index
        self.closed = False

    def execute(self, sql):
        self.events.append(("execute", sql))
        if self.fail_index and sql.startswith(self.fail_index):
            raise LookupError("injected index failure")
        if sql.startswith("PRAGMA table_info"):
            return FakeCursor([(0, "payload")])
        return FakeCursor()

    def close(self):
        if self.closed:
            raise AssertionError("Connection closed twice")
        self.closed = True
        self.events.append(("close",))


class FakeFrame:
    columns = ["payload"]

    def __init__(self, events, fail_write=False):
        self.events = events
        self.fail_write = fail_write
        self.loc = self

    def __getitem__(self, selection):
        if not isinstance(selection, tuple) or selection[0] != slice(None):
            raise AssertionError("Unexpected DataFrame selection")
        self.events.append(("select", selection[1]))
        return self

    def copy(self):
        self.events.append(("copy",))
        return self

    def __len__(self):
        return 0

    def to_sql(self, **kwargs):
        self.events.append(("to_sql", kwargs))
        if self.fail_write:
            raise RuntimeError("injected SQL writer failure")


class AlternateWriterCleanupTests(unittest.TestCase):
    def run_writer(self, *, fail_schema=False, fail_write=False,
                   fail_index=None, index_cols=None, unique_cols=None):
        events = []
        connection = FakeConnection(events, fail_index=fail_index)

        def connect(name):
            events.append(("connect", name))
            return connection

        def ensure_schema(cnx, table, frame, required, debug=False):
            self.assertIs(cnx, connection)
            self.assertEqual(table, "sampleSrc")
            events.append(("schema", tuple(required), debug))
            if fail_schema:
                raise ValueError("injected schema failure")

        writer = isolated_writer(ensure_schema)
        frame = FakeFrame(events, fail_write=fail_write)
        with patch.object(sqlite3, "connect", side_effect=connect):
            def invoke():
                return writer(
                    "in-memory-fake", frame,
                    IndexCols=index_cols, UniqueIndexCols=unique_cols,
                )
            if fail_schema:
                with self.assertRaisesRegex(ValueError, "schema failure"):
                    invoke()
            elif fail_write:
                with self.assertRaisesRegex(RuntimeError, "writer failure"):
                    invoke()
            elif fail_index:
                with self.assertRaisesRegex(LookupError, "index failure"):
                    invoke()
            else:
                self.assertIsNone(invoke())
        self.assertTrue(connection.closed)
        self.assertEqual([e[0] for e in events].count("close"), 1)
        self.assertEqual(events[-1], ("close",))
        return events, connection

    def test_success_keeps_connection_until_both_index_types_finish(self):
        events, connection = self.run_writer(
            index_cols=["payload"], unique_cols=["payload"],
        )
        names = [e[0] for e in events]
        self.assertEqual(names[:4], ["select", "copy", "connect", "schema"])
        self.assertEqual(names[4], "to_sql")
        write = events[4][1]
        self.assertIs(write["con"], connection)
        self.assertEqual(
            {key: write[key] for key in
             ("name", "if_exists", "dtype", "index", "index_label")},
            {"name": "sampleSrc", "if_exists": "replace", "dtype": None,
             "index": True, "index_label": "index"},
        )
        queries = [x[1] for x in events if x[0] == "execute"]
        self.assertEqual(len(queries), 3)
        self.assertTrue(queries[0].startswith("PRAGMA table_info"))
        self.assertTrue(queries[1].startswith("CREATE INDEX IF NOT EXISTS"))
        self.assertTrue(queries[2].startswith("CREATE UNIQUE INDEX IF NOT EXISTS"))

    def test_schema_failure_closes_connection_and_preserves_exception(self):
        events, _ = self.run_writer(fail_schema=True)
        self.assertEqual(
            [e[0] for e in events],
            ["select", "copy", "connect", "schema", "close"],
        )

    def test_to_sql_failure_closes_connection_and_preserves_exception(self):
        events, _ = self.run_writer(fail_write=True)
        self.assertEqual(
            [e[0] for e in events],
            ["select", "copy", "connect", "schema", "to_sql", "close"],
        )

    def test_regular_index_failure_closes_connection(self):
        events, _ = self.run_writer(
            index_cols=["payload"], fail_index="CREATE INDEX",
        )
        self.assertEqual(
            [e[0] for e in events][-3:],
            ["execute", "execute", "close"],
        )

    def test_unique_index_failure_closes_connection(self):
        events, _ = self.run_writer(
            unique_cols=["payload"], fail_index="CREATE UNIQUE INDEX",
        )
        self.assertEqual(
            [e[0] for e in events][-3:],
            ["execute", "execute", "close"],
        )


if __name__ == "__main__":
    unittest.main()
