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
            'ALTER TABLE "__bl001_stage_',
            'CREATE INDEX "ix_sampleSrc_index"',
            'CREATE INDEX "text_Index"',
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
