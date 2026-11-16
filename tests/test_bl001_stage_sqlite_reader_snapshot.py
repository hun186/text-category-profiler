"""Real private subprocess reader-snapshot consistency acceptance."""
from contextlib import redirect_stdout
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path
import tempfile
import unittest

from scripts.bl001_stage_sqlite_reader_snapshot import (
    main, private_reader_snapshot, _writer_index_contract,
)


class PrivateReaderSnapshotTests(unittest.TestCase):
    def test_index_names_are_not_enough_to_certify_columns(self):
        with tempfile.TemporaryDirectory(prefix="ki012-index-negative-") as tmp:
            path = Path(tmp) / "fake-index.sqlite3"
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE sampleSrc ("index" INTEGER, "text" TEXT, "label" TEXT)')
                db.execute('CREATE INDEX "ix_sampleSrc_index" ON sampleSrc("index")')
                db.execute('CREATE INDEX "text_Index" ON sampleSrc("label")')
                self.assertFalse(_writer_index_contract(db))
                db.execute('DROP INDEX "text_Index"')
                db.execute('CREATE INDEX "text_Index" ON sampleSrc("text")')
                self.assertTrue(_writer_index_contract(db))
                db.execute('DROP INDEX "ix_sampleSrc_index"')
                db.execute('CREATE UNIQUE INDEX "ix_sampleSrc_index" ON sampleSrc("index")')
                self.assertFalse(_writer_index_contract(db))


    @classmethod
    def setUpClass(cls):
        try:
            import pandas  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pandas needed")

    def test_reader_remains_old_until_swap_commits(self):
        report = private_reader_snapshot(rows=20)
        self.assertEqual(report["status"], "PASS_PRIVATE_READER_SNAPSHOT")
        self.assertEqual(report["scope"], "private_tempfile_only_no_workpool")
        self.assertTrue(report["old_snapshot_preserved_during_swap"])
        self.assertTrue(report["writer_waited_for_reader_release"])
        self.assertTrue(report["new_rows_visible_after_commit"])
        self.assertTrue(report["dependent_view_consistent"])
        self.assertTrue(report["text_indexes_present"])
        self.assertEqual(report["candidate_tables_remaining"], 0)
        self.assertFalse(report["production_workpool_verified"])

    def test_cli_is_private_only_and_bounded(self):
        for args in (["--rows", "9"], ["--rows", "501"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(args), 1)
        with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exc:
            main(["--db", "WorkPool/live.sqlite3"])
        self.assertEqual(exc.exception.code, 2)

    def test_small_cli_returns_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["--rows", "15"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "PASS_PRIVATE_READER_SNAPSHOT")


if __name__ == "__main__":
    unittest.main()
