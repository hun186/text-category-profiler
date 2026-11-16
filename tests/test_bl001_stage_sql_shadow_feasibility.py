"""Non-production feasibility characterization for transactional shadow table swap.

This is NOT an implementation of the Stage-local writer. The tests expose both
the rollback benefit of a staged replacement and the pandas-generated index
name incompatibility that must be resolved before changing production.
Only private sqlite3 TemporaryDirectory files are used.
"""

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest


class StageSQLShadowSwapFeasibilityTests(unittest.TestCase):
    def setUp(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas required for real private SQLite characterization")
        self.pd = pd
        self.tmp = tempfile.TemporaryDirectory(prefix="bl001-shadow-feasibility-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "prototype.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        pd.DataFrame({
            "text": ["原始內容"], "label": ["TW Original"],
        }).to_sql(name="sampleSrc", con=self.db, if_exists="replace")
        self.db.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text")')
        self.db.execute('CREATE TABLE "unrelated" (note TEXT)')
        self.db.execute('INSERT INTO "unrelated" VALUES ("keep")')
        self.db.commit()
        self.original_index_names = set(self._indexes("sampleSrc"))
        self.assertIn("text_Index", self.original_index_names)
        self.assertIn("ix_sampleSrc_index", self.original_index_names)

    def _indexes(self, table):
        return [
            row[1] for row in self.db.execute(f'PRAGMA index_list("{table}")')
        ]

    def _rows(self):
        return self.db.execute(
            'SELECT "text", "label" FROM "sampleSrc" ORDER BY "index"'
        ).fetchall()

    def _prepare(self):
        # No production table changes while pandas commits its own to_sql.
        self.pd.DataFrame({
            "text": ["候選新內容"], "label": ["TW Candidate"],
        }).to_sql(name="__bl001_candidate", con=self.db, if_exists="fail")
        self.assertEqual(self._rows(), [("原始內容", "TW Original")])

    def test_rollback_after_drop_and_rename_preserves_original_table_and_indexes(self):
        self._prepare()
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute('DROP TABLE "sampleSrc"')
        self.db.execute('ALTER TABLE "__bl001_candidate" RENAME TO "sampleSrc"')
        self.db.rollback()  # An injected failure before index recreation.

        self.assertEqual(self._rows(), [("原始內容", "TW Original")])
        self.assertEqual(set(self._indexes("sampleSrc")), self.original_index_names)
        self.assertEqual(
            self.db.execute('SELECT note FROM "unrelated"').fetchall(),
            [("keep",)],
        )
        # Committed staging is still present: a crashed writer can orphan it.
        self.assertIsNotNone(self.db.execute(
            'SELECT name FROM sqlite_master WHERE type="table" '
            'AND name="__bl001_candidate"'
        ).fetchone())
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_successful_shadow_rename_changes_pandas_auxiliary_index_name(self):
        self._prepare()
        staged_indexes = self._indexes("__bl001_candidate")
        self.assertIn("ix___bl001_candidate_index", staged_indexes)
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute('DROP TABLE "sampleSrc"')
        self.db.execute('ALTER TABLE "__bl001_candidate" RENAME TO "sampleSrc"')
        self.db.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text")')
        self.db.commit()

        self.assertEqual(self._rows(), [("候選新內容", "TW Candidate")])
        current_indexes = set(self._indexes("sampleSrc"))
        self.assertIn("text_Index", current_indexes)
        self.assertIn("ix___bl001_candidate_index", current_indexes)
        self.assertNotIn("ix_sampleSrc_index", current_indexes)
        self.assertEqual(
            self.db.execute('SELECT note FROM "unrelated"').fetchall(),
            [("keep",)],
        )
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")


if __name__ == "__main__":
    unittest.main()
