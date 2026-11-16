"""Private-disk, real pandas + sqlite3 acceptance for KI-012 atomic stage writer.

No WorkPool or production database paths are accepted. These tests compare
actual stage table columns/rows/indexes against pandas's legacy output,
inject failures in the atomic swap, and kill the writer before commit.
"""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from text_category_profiler.data.stage_sql import write_stage_sql


class AtomicStageSQLTests(unittest.TestCase):
    def setUp(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas required for private SQLite atomic integration")
        self.pd = pd
        self.private = tempfile.TemporaryDirectory(prefix="ki012-atomic-stage-private-")
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)

    def _write(self, name, frame, factory=sqlite3.connect, columns=None):
        filename = self.root / name
        write_stage_sql(str(filename), frame, [] if columns is None else columns, factory)
        return filename

    @staticmethod
    def _schema_and_rows(path):
        with closing(sqlite3.connect(path)) as db:
            columns = tuple(
                (row[1], row[2], row[3], row[4], row[5])
                for row in db.execute('PRAGMA table_info("sampleSrc")')
            )
            indexes = {}
            for entry in db.execute('PRAGMA index_list("sampleSrc")'):
                name = entry[1]
                keys = tuple(
                    (row[2], row[3], row[4])
                    for row in db.execute(
                        'PRAGMA index_xinfo("' + name.replace('"', '""') + '")'
                    ) if row[5] == 1
                )
                indexes[name] = (entry[2], entry[3], entry[4], keys)
            data = tuple(db.execute('SELECT * FROM "sampleSrc" ORDER BY "index"'))
            other = db.execute("PRAGMA integrity_check").fetchone()[0]
            stage_names = tuple(
                row[0] for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name LIKE '__bl001_stage_%'"
                )
            )
            return columns, indexes, data, other, stage_names

    def test_output_matches_legacy_default_named_multiindex_and_empty(self):
        pd = self.pd
        frames = (
            pd.DataFrame({"text": ["台灣", "桃園"], "label": ["A", "B"]}),
            pd.DataFrame({"text": ["中文"], "label": ["N"]},
                         index=pd.Index(["中"], name="uid")),
            pd.DataFrame({"text": ["多層"], "label": ["M"]},
                         index=pd.MultiIndex.from_tuples(
                             [("第一組", 8)], names=["group", "unit"]
                         )),
            pd.DataFrame({"text": pd.Series(dtype=str),
                          "label": pd.Series(dtype=str)}),
        )
        for number, frame in enumerate(frames):
            with self.subTest(index=frame.index.names, case=number):
                baseline = self.root / f"legacy-{number}.sqlite3"
                with closing(sqlite3.connect(baseline)) as db:
                    frame.to_sql(name="sampleSrc", con=db, if_exists="replace")
                    db.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text");')
                    db.commit()
                atomic = self._write(f"atomic-{number}.sqlite3", frame)
                expected = self._schema_and_rows(baseline)
                actual = self._schema_and_rows(atomic)
                self.assertEqual(actual, expected)
                self.assertIn("text_Index", actual[1])
                self.assertEqual(actual[3], "ok")
                self.assertEqual(actual[4], ())

    def test_repeated_replace_and_other_tables_are_preserved(self):
        pd = self.pd
        path = self._write("repeated.sqlite3",
                           pd.DataFrame({"text": ["舊"], "label": ["O"]}))
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE "unrelated" (note TEXT)')
            db.execute('INSERT INTO "unrelated" VALUES ("保留")')
            db.commit()
        self._write("repeated.sqlite3",
                    pd.DataFrame({"text": ["新"], "label": ["N"]},
                                 index=pd.Index([12], name="new_id")))
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(
                db.execute('SELECT "text", "label" FROM "sampleSrc"').fetchall(),
                [("新", "N")],
            )
            self.assertEqual(
                db.execute('SELECT note FROM "unrelated"').fetchall(),
                [("保留",)],
            )
            names = {row[1] for row in db.execute('PRAGMA index_list("sampleSrc")')}
            self.assertEqual(names, {"ix_sampleSrc_new_id", "text_Index"})
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], "ok")

    def test_rollback_on_swap_or_index_failure_keeps_prior_committed_data(self):
        pd = self.pd
        before = pd.DataFrame({"text": ["原本"], "label": ["P"]})
        candidate = pd.DataFrame({"text": ["不得提交"], "label": ["X"]})
        triggers = (
            'DROP TABLE IF EXISTS "sampleSrc"',
            'CREATE TABLE "sampleSrc"',
            'INSERT INTO "sampleSrc"',
            'CREATE INDEX "ix_sampleSrc_index"',
            'CREATE INDEX "text_Index"',
            'DROP TABLE "__bl001_stage_',
        )

        for attempt, trigger in enumerate(triggers):
            with self.subTest(at=trigger):
                path = self._write(f"rollback-{attempt}.sqlite3", before)
                original = self._schema_and_rows(path)

                class FailInSwap(sqlite3.Connection):
                    def execute(self, sql, *args):
                        if sql.startswith(trigger):
                            raise RuntimeError("injected swap failure")
                        return super().execute(sql, *args)

                with self.assertRaisesRegex(RuntimeError, "injected swap failure"):
                    self._write(
                        f"rollback-{attempt}.sqlite3", candidate,
                        factory=lambda name: sqlite3.connect(
                            name, factory=FailInSwap
                        ),
                    )
                self.assertEqual(self._schema_and_rows(path), original)

    def test_dependent_view_survives_replacement_and_failed_index_build(self):
        pd = self.pd
        original = pd.DataFrame({"text": ["舊新聞"], "label": ["OLD"]})
        replacement = pd.DataFrame({"text": ["新新聞"], "label": ["NEW"]})
        path = self._write("view.sqlite3", original)
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE VIEW "text_view" AS SELECT "text" FROM "sampleSrc"')
            db.commit()
            original_view_sql = db.execute(
                "SELECT sql FROM sqlite_master WHERE type='view' AND name='text_view'"
            ).fetchone()[0]

        class FailIndex(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql.startswith('CREATE INDEX "text_Index"'):
                    raise RuntimeError("injected index failure with dependent view")
                return super().execute(sql, *args)

        with self.assertRaisesRegex(RuntimeError, "injected index failure"):
            self._write(
                "view.sqlite3", replacement,
                factory=lambda name: sqlite3.connect(name, factory=FailIndex),
            )
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(
                db.execute('SELECT "text" FROM "text_view"').fetchall(),
                [("舊新聞",)],
            )

        self._write("view.sqlite3", replacement)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(
                db.execute('SELECT "text" FROM "text_view"').fetchall(),
                [("新新聞",)],
            )
            self.assertEqual(
                db.execute('SELECT "text", "label" FROM "sampleSrc"').fetchall(),
                [("新新聞", "NEW")],
            )
            self.assertEqual(
                db.execute(
                    "SELECT sql FROM sqlite_master WHERE type='view' AND name='text_view'"
                ).fetchone()[0], original_view_sql,
            )
            self.assertEqual(
                {row[1] for row in db.execute('PRAGMA index_list("sampleSrc")')},
                {"ix_sampleSrc_index", "text_Index"},
            )
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_inbound_foreign_key_cascade_is_refused_without_data_loss(self):
        pd = self.pd
        path = self._write(
            "inbound-foreign-key.sqlite3",
            pd.DataFrame({"text": ["舊資料"], "label": ["KEEP"]}),
        )
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute('CREATE UNIQUE INDEX "parent_text_key" ON "sampleSrc"("text")')
            db.execute(
                'CREATE TABLE "child" ('
                '"ref" TEXT REFERENCES "sampleSrc"("text") ON DELETE CASCADE)'
            )
            db.execute('INSERT INTO "child" VALUES ("舊資料")')
            db.commit()

        def connect_with_fk(name):
            result = sqlite3.connect(name)
            result.execute("PRAGMA foreign_keys=ON")
            return result

        before = self._schema_and_rows(path)
        with self.assertRaisesRegex(ValueError, "inbound foreign-key dependency"):
            self._write(
                "inbound-foreign-key.sqlite3",
                pd.DataFrame({"text": ["新資料"], "label": ["NEW"]}),
                factory=connect_with_fk,
            )
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA foreign_keys=ON")
            self.assertEqual(
                db.execute('SELECT "ref" FROM "child"').fetchall(),
                [("舊資料",)],
            )
            self.assertEqual(
                db.execute('SELECT "text", "label" FROM "sampleSrc"').fetchall(),
                [("舊資料", "KEEP")],
            )
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self._schema_and_rows(path), before)

    def test_attached_trigger_is_not_silently_dropped(self):
        pd = self.pd
        path = self._write(
            "trigger-preservation.sqlite3",
            pd.DataFrame({"text": ["舊資料"], "label": ["KEEP"]}),
        )
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE "audit_rows" (value TEXT)')
            db.execute(
                'CREATE TRIGGER "sampleSrc_insert_log" '
                'AFTER INSERT ON "sampleSrc" '
                'BEGIN INSERT INTO "audit_rows" VALUES (NEW."text"); END'
            )
            db.commit()
        before = self._schema_and_rows(path)
        with self.assertRaisesRegex(ValueError, "trigger dependency"):
            self._write(
                "trigger-preservation.sqlite3",
                pd.DataFrame({"text": ["不得提交"], "label": ["NEW"]}),
            )
        with closing(sqlite3.connect(path)) as db:
            self.assertIsNotNone(db.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' "
                "AND name='sampleSrc_insert_log'"
            ).fetchone())
            self.assertEqual(
                db.execute('SELECT "text" FROM "sampleSrc"').fetchall(),
                [("舊資料",)],
            )
            db.execute(
                'INSERT INTO "sampleSrc" ("index", "text", "label") '
                'VALUES (1, "新記錄", "OK")'
            )
            db.commit()
            self.assertEqual(
                db.execute('SELECT value FROM audit_rows').fetchall(),
                [("新記錄",)],
            )
        self.assertEqual(before[3], "ok")

    def test_custom_indexes_are_not_silently_dropped_during_stage_swap(self):
        pd = self.pd
        for number, index_ddl in enumerate((
            'CREATE INDEX "manual_search" ON "sampleSrc"("label")',
            'CREATE UNIQUE INDEX "unique_text" ON "sampleSrc"("text")',
            'CREATE INDEX "ix_sampleSrc_label" '
            'ON "sampleSrc"("label" COLLATE NOCASE)',
        )):
            with self.subTest(variant=number):
                filename = f"index-preservation-{number}.sqlite3"
                path = self._write(
                    filename,
                    pd.DataFrame({"text": ["舊資料"], "label": ["KEEP"]}),
                )
                with closing(sqlite3.connect(path)) as db:
                    db.execute(index_ddl)
                    db.commit()
                original = self._schema_and_rows(path)
                with self.assertRaisesRegex(ValueError,
                                            "Unsafe existing sampleSrc index"):
                    self._write(
                        filename,
                        pd.DataFrame({"text": ["不得提交"], "label": ["NEW"]}),
                    )
                self.assertEqual(self._schema_and_rows(path), original)

    def test_modified_text_index_cannot_be_silently_weakened(self):
        pd = self.pd
        filename = "modified-text-index.sqlite3"
        path = self._write(
            filename, pd.DataFrame({"text": ["原本"], "label": ["KEEP"]})
        )
        with closing(sqlite3.connect(path)) as db:
            db.execute('DROP INDEX "text_Index"')
            db.execute(
                'CREATE UNIQUE INDEX "text_Index" ON "sampleSrc"("text")'
            )
            db.commit()
        original = self._schema_and_rows(path)
        with self.assertRaisesRegex(ValueError, "Unsafe existing sampleSrc index"):
            self._write(
                filename,
                pd.DataFrame({"text": ["不得提交"], "label": ["NEW"]}),
            )
        self.assertEqual(self._schema_and_rows(path), original)

    def test_unrelated_foreign_keys_and_triggers_do_not_block_stage(self):
        pd = self.pd
        path = self._write(
            "unrelated-dependencies.sqlite3",
            pd.DataFrame({"text": ["舊"], "label": ["A"]}),
        )
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE "parent" ("id" INTEGER PRIMARY KEY)')
            db.execute(
                'CREATE TABLE "child" ('
                '"ref" INTEGER REFERENCES "parent"("id") ON DELETE CASCADE)'
            )
            db.execute('CREATE TABLE "audit_rows" ("note" TEXT)')
            db.execute(
                'CREATE TRIGGER "parent_insert_log" AFTER INSERT ON "parent" '
                'BEGIN INSERT INTO "audit_rows" VALUES ("seen"); END'
            )
            db.execute('INSERT INTO "parent" VALUES (1)')
            db.execute('INSERT INTO "child" VALUES (1)')
            db.commit()
        self._write("unrelated-dependencies.sqlite3",
                    pd.DataFrame({"text": ["新"], "label": ["B"]}))
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(
                db.execute('SELECT "text" FROM "sampleSrc"').fetchall(),
                [("新",)],
            )
            self.assertEqual(
                db.execute('SELECT "ref" FROM "child"').fetchall(), [(1,)],
            )
            self.assertIsNotNone(db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' "
                "AND name='parent_insert_log'"
            ).fetchone())

    def test_failed_preflight_does_not_connect_or_replace(self):
        pd = self.pd
        path = self._write("preflight.sqlite3",
                           pd.DataFrame({"text": ["重要"], "label": ["P"]}))
        original = self._schema_and_rows(path)
        with self.assertRaisesRegex(ValueError, "requires a 'text' column"):
            self._write(
                "preflight.sqlite3", pd.DataFrame({"label": ["錯誤"]}),
                factory=lambda name: self.fail("invalid input opened DB"),
            )
        self.assertEqual(self._schema_and_rows(path), original)

    def test_killed_writer_before_commit_preserves_old_table_index_and_integrity(self):
        from scripts.bl001_stage_sqlite_atomicity_probe import run_probe

        outcome = run_probe()
        self.assertEqual(outcome["status"], "PASS_ATOMICITY", outcome)
        self.assertTrue(outcome["original_preserved"])
        self.assertFalse(outcome["new_partial_rows_present"])
        self.assertTrue(outcome["text_index_present"])
        self.assertEqual(outcome["integrity_check"], "ok")
        self.assertEqual(outcome["scope"], "private_tempfile_only_no_workpool")


if __name__ == "__main__":
    unittest.main()
