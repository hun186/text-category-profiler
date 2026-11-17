"""No-service canonical SQLite atomic replace regression on private temp files."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from text_category_profiler.data.canonical_sql_atomic import (
    replace_canonical_table,
)

try:
    import pandas as pd
except ImportError:
    pd = None


@unittest.skipIf(pd is None, "pandas not installed in lightweight CI")
class CanonicalAtomicReplaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bl001-canon-atomic-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "private.sql3"

    def conn(self):
        return sqlite3.connect(self.path)

    def old(self):
        with closing(self.conn()) as db:
            db.execute('CREATE TABLE "sampleSrc" ("index" INTEGER, "text" TEXT, "OutLabel" TEXT)')
            db.execute('INSERT INTO sampleSrc VALUES (0,"old","KEEP")')
            db.execute('CREATE INDEX "ix_sampleSrc_index" ON sampleSrc("index")')
            db.commit()

    def row(self):
        with closing(self.conn()) as db:
            return db.execute("SELECT text,OutLabel FROM sampleSrc").fetchall()

    def indexes(self):
        with closing(self.conn()) as db:
            return db.execute("PRAGMA index_list(sampleSrc)").fetchall()

    def test_canonical_default_and_optional_indexes_preserve_pandas_schema(self):
        self.old()
        frame = pd.DataFrame({"text": ["中文", "abc"], "OutLabel": ["A", "B"]})
        with closing(self.conn()) as db:
            replace_canonical_table(
                db, frame, table="sampleSrc", dtype=None,
                index_label=None, index_cols=["text"],
            )
        self.assertEqual(self.row(), [("中文", "A"), ("abc", "B")])
        self.assertEqual(
            {item[1] for item in self.indexes()},
            {"ix_sampleSrc_index", "text_Index"},
        )

    def test_reopen_empty_dataframe_and_custom_table(self):
        frame = pd.DataFrame({"text": pd.Series(dtype=str), "label": pd.Series(dtype=str)})
        with closing(self.conn()) as db:
            replace_canonical_table(db, frame, table="records", dtype=None,
                                    index_label=None, index_cols=[])
        with closing(self.conn()) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM records").fetchone(), (0,))
            self.assertEqual(
                {r[1] for r in db.execute("PRAGMA index_list(records)")},
                {"ix_records_index"},
            )

    def test_unknown_existing_index_rejects_and_preserves_rows(self):
        self.old()
        with closing(self.conn()) as db:
            db.execute('CREATE INDEX "custom_business" ON sampleSrc("OutLabel")')
            db.commit()
        frame = pd.DataFrame({"text": ["new"], "OutLabel": ["N"]})
        with closing(self.conn()) as db:
            with self.assertRaisesRegex(ValueError, "Unsafe existing index"):
                replace_canonical_table(db, frame, table="sampleSrc",
                                        dtype=None, index_label=None, index_cols=[])
        self.assertEqual(self.row(), [("old", "KEEP")])
        self.assertIn("custom_business", {x[1] for x in self.indexes()})

    def test_trigger_and_inbound_fk_reject_before_drop(self):
        frame = pd.DataFrame({"text": ["new"], "OutLabel": ["N"]})
        for constraint in ("trigger", "foreign_key"):
            with self.subTest(constraint=constraint):
                if self.path.exists():
                    self.path.unlink()
                self.old()
                with closing(self.conn()) as db:
                    if constraint == "trigger":
                        db.execute('CREATE TRIGGER block_delete BEFORE DELETE ON sampleSrc BEGIN SELECT 1; END')
                    else:
                        db.execute('CREATE TABLE dependent(x INTEGER REFERENCES sampleSrc("index"))')
                    db.commit()
                with closing(self.conn()) as db:
                    with self.assertRaisesRegex(ValueError, "Unsafe"):
                        replace_canonical_table(db, frame, table="sampleSrc",
                                                dtype=None, index_label=None, index_cols=[])
                self.assertEqual(self.row(), [("old", "KEEP")])

    def test_missing_index_column_rolls_back_without_data_loss(self):
        self.old()
        frame = pd.DataFrame({"text": ["new"], "OutLabel": ["N"]})
        with closing(self.conn()) as db:
            with self.assertRaisesRegex(ValueError, "Requested index column absent"):
                replace_canonical_table(db, frame, table="sampleSrc",
                                        dtype=None, index_label=None, index_cols=["nope"])
        self.assertEqual(self.row(), [("old", "KEEP")])

    def test_failed_staging_does_not_drop_original(self):
        self.old()
        class FailFrame:
            def to_sql(self, **kw):
                raise RuntimeError("stage interrupted")
        with closing(self.conn()) as db:
            with self.assertRaisesRegex(RuntimeError, "stage interrupted"):
                replace_canonical_table(db, FailFrame(), table="sampleSrc",
                                        dtype=None, index_label=None, index_cols=[])
        self.assertEqual(self.row(), [("old", "KEEP")])

    def test_injected_index_failure_rolls_back_and_preserves_index(self):
        self.old()
        class FaultConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                if sql.startswith('CREATE INDEX "text_Index"'):
                    raise RuntimeError("index failed")
                return super().execute(sql, parameters)
        frame = pd.DataFrame({"text": ["new"], "OutLabel": ["N"]})
        with closing(sqlite3.connect(self.path, factory=FaultConnection)) as db:
            with self.assertRaisesRegex(RuntimeError, "index failed"):
                replace_canonical_table(db, frame, table="sampleSrc",
                                        dtype=None, index_label=None, index_cols=["text"])
        self.assertEqual(self.row(), [("old", "KEEP")])
        self.assertEqual({r[1] for r in self.indexes()}, {"ix_sampleSrc_index"})

    def test_duplicate_requested_index_names_fail_closed(self):
        self.old()
        frame = pd.DataFrame({"text": ["new"], "OutLabel": ["N"]})
        with closing(self.conn()) as db:
            with self.assertRaisesRegex(ValueError, "Conflicting target index names"):
                replace_canonical_table(db, frame, table="sampleSrc",
                                        dtype=None, index_label=None,
                                        index_cols=["text", "text"])
        self.assertEqual(self.row(), [("old", "KEEP")])


if __name__ == "__main__":
    unittest.main()
