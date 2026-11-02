"""BL-001 bounded pandas + real in-memory SQLite writer characterization.

No on-disk database, WorkPool, model, external SQL service or production import.
Only the two canonical writer ASTs are executed; schema creation is deliberately
injected for the alternate writer, not a full runtime/transaction acceptance.
"""
import ast
import json
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
import uuid

try:
    import pandas as pd
except ImportError:
    pd = None


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "text_category_profiler" / "data" / "df_utils.py"


def isolated_writer(name, **dependencies):
    tree = ast.parse(CANONICAL.read_text(encoding="utf-8-sig"))
    functions = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    if len(functions) != 1:
        raise AssertionError(f"Expected exactly one {name} function")
    scope = dict(dependencies)
    exec(
        compile(ast.Module(body=functions, type_ignores=[]), str(CANONICAL), "exec"),
        scope,
    )
    return scope[name]


class TrackedSqliteConnection(sqlite3.Connection):
    def close(self):
        self.was_closed = True
        super().close()


@unittest.skipIf(pd is None, "pandas not installed in this test environment")
class RealMemorySqliteContracts(unittest.TestCase):
    def setUp(self):
        # A live anchor keeps this private named in-memory database available
        # after the writer's own connection closes.
        self.uri = "file:bl001_" + uuid.uuid4().hex + "?mode=memory&cache=shared"
        self.original_connect = sqlite3.connect
        self.anchor = self.original_connect(self.uri, uri=True)
        self.addCleanup(self.anchor.close)
        self.connections = []

    def writer_connect(self, _ignored_name):
        connection = self.original_connect(
            self.uri, uri=True, factory=TrackedSqliteConnection,
        )
        self.connections.append(connection)
        return connection

    def assert_writer_closed(self):
        self.assertEqual(len(self.connections), 1)
        self.assertTrue(self.connections[0].was_closed)
        with self.assertRaises(sqlite3.ProgrammingError):
            self.connections[0].execute("SELECT 1")

    @staticmethod
    def no_schema_write(connection, table, frame, columns, debug=False):
        # Replaces the runtime's schema adapter. Pandas owns temporary table
        # creation in these controlled replace/fail scenarios.
        if table != "sampleSrc":
            raise AssertionError("Unexpected table name")

    def test_canonical_writer_persists_unicode_json_and_closes(self):
        writer = isolated_writer(
            "dfToSQL", lite=sqlite3, json=json, MPlogger=lambda: object(),
        )
        frame = pd.DataFrame({
            "payload": [{"城市": "台北"}, ["甲", "乙"]],
        })
        with patch.object(sqlite3, "connect", side_effect=self.writer_connect):
            writer("not-an-on-disk-file", frame, MPLOGGER=object())
        self.assert_writer_closed()
        values = self.anchor.execute(
            'SELECT "payload" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()
        self.assertEqual(values, [
            (json.dumps({"城市": "台北"}, ensure_ascii=False),),
            (json.dumps(["甲", "乙"], ensure_ascii=False),),
        ])

    def test_alternate_writer_keeps_saved_values_and_real_indexes(self):
        writer = isolated_writer(
            "dfToSQL_new_appending", ensure_schema=self.no_schema_write,
        )
        frame = pd.DataFrame({"payload": [{"城市": "台北"}, "plain"]})
        with patch.object(sqlite3, "connect", side_effect=self.writer_connect):
            writer(
                "not-an-on-disk-file", frame, preserve_index=False,
                IndexCols=["payload"], UniqueIndexCols=["payload"],
            )
        self.assert_writer_closed()
        self.assertEqual(
            self.anchor.execute('SELECT payload FROM "sampleSrc"').fetchall(),
            [(json.dumps({"城市": "台北"}, ensure_ascii=False),), ("plain",)],
        )
        indexes = {
            row[0] for row in self.anchor.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
        }
        self.assertIn("sampleSrc_payload_idx", indexes)
        self.assertIn("sampleSrc_payload_uniq", indexes)

    def test_alternate_if_exists_fail_preserves_old_rows_and_closes(self):
        self.anchor.execute('CREATE TABLE "sampleSrc" ("payload" TEXT)')
        self.anchor.execute(
            'INSERT INTO "sampleSrc" ("payload") VALUES (?)', ("old",),
        )
        self.anchor.commit()
        writer = isolated_writer(
            "dfToSQL_new_appending", ensure_schema=self.no_schema_write,
        )
        with patch.object(sqlite3, "connect", side_effect=self.writer_connect):
            with self.assertRaisesRegex(ValueError, "already exists"):
                writer(
                    "not-an-on-disk-file",
                    pd.DataFrame({"payload": ["new"]}),
                    preserve_index=False, if_exists="fail",
                )
        self.assert_writer_closed()
        self.assertEqual(
            self.anchor.execute('SELECT payload FROM "sampleSrc"').fetchall(),
            [("old",)],
        )


if __name__ == "__main__":
    unittest.main()
