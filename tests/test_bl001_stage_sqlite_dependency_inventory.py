"""Private SQLite copies only: inbound-FK/trigger metadata scan."""
from contextlib import closing, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_dependency_inventory import (
    inspect_offline_replacement_dependencies, main,
)


class OfflineReplacementDependencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ki012-private-deps-")
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "offline.sqlite3"
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE TABLE "sampleSrc" ("text" TEXT)')
            db.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text")')
            db.commit()

    def test_no_dependencies_does_not_claim_approval_or_change_bytes(self):
        before = self.db.read_bytes()
        outcome = inspect_offline_replacement_dependencies(self.db)
        self.assertEqual(outcome["status"], "NO_DEPENDENCIES_OBSERVED")
        self.assertEqual(outcome["trigger_count"], 0)
        self.assertEqual(outcome["inbound_foreign_key_count"], 0)
        self.assertFalse(outcome["replacement_authorized"])
        self.assertFalse(outcome["production_workpool_verified"])
        self.assertEqual(self.db.read_bytes(), before)

    def test_cascade_foreign_key_and_attached_trigger_require_review(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE UNIQUE INDEX "unique_text" ON "sampleSrc"("text")')
            db.execute(
                'CREATE TABLE "child" (ref TEXT REFERENCES '
                '"sampleSrc"("text") ON DELETE CASCADE)'
            )
            db.execute(
                'CREATE TRIGGER "sampleSrc_insert_check" '
                'AFTER INSERT ON "sampleSrc" BEGIN SELECT 1; END'
            )
            db.commit()
        before = self.db.read_bytes()
        report = inspect_offline_replacement_dependencies(self.db)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["trigger_count"], 1)
        self.assertEqual(report["attached_trigger_names"],
                         ["sampleSrc_insert_check"])
        self.assertEqual(report["inbound_foreign_key_count"], 1)
        self.assertEqual(report["referencing_table_names"], ["child"])
        self.assertFalse(report["replacement_authorized"])
        self.assertEqual(self.db.read_bytes(), before)

    def test_multicolumn_foreign_key_counts_constraint_only_once(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('ALTER TABLE "sampleSrc" ADD COLUMN "label" TEXT')
            db.execute(
                'CREATE UNIQUE INDEX "unique_pair" '
                'ON "sampleSrc"("text", "label")'
            )
            db.execute(
                'CREATE TABLE "composite_child" ('
                'a TEXT, b TEXT, '
                'FOREIGN KEY(a, b) REFERENCES "sampleSrc"("text", "label"))'
            )
            db.commit()
        result = inspect_offline_replacement_dependencies(self.db)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["inbound_foreign_key_count"], 1)
        self.assertEqual(result["referencing_table_names"], ["composite_child"])
        self.assertFalse(result["replacement_authorized"])

    def test_unrelated_fk_and_trigger_are_not_inbound(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute('CREATE TABLE "parent" (id INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE "child" (ref INTEGER REFERENCES parent(id))')
            db.execute(
                'CREATE TRIGGER "parent_trigger" AFTER INSERT ON parent '
                'BEGIN SELECT 1; END'
            )
            db.commit()
        report = inspect_offline_replacement_dependencies(self.db)
        self.assertEqual(report["status"], "NO_DEPENDENCIES_OBSERVED")

    def test_candidate_and_disallowed_source_do_not_receive_clear_verdict(self):
        with closing(sqlite3.connect(self.db)) as db:
            db.execute(
                'CREATE TABLE "__bl001_stage_'
                + "a" * 32 + '" ("text" TEXT)'
            )
            db.commit()
        self.assertEqual(
            inspect_offline_replacement_dependencies(self.db)["status"],
            "REVIEW_REQUIRED",
        )
        pool = Path(self.tmp.name) / "WorkPool-local"
        pool.mkdir()
        copied = pool / "live.sqlite3"
        shutil.copyfile(self.db, copied)
        result = inspect_offline_replacement_dependencies(copied)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("workpool_path_not_allowed", result["issues"])
        alias = Path(self.tmp.name) / "hardlink.sqlite3"
        try:
            os.link(self.db, alias)
        except (OSError, NotImplementedError):
            pass
        else:
            from unittest.mock import patch
            with patch(
                "scripts.bl001_stage_sqlite_dependency_inventory.inventory_offline_copy",
                side_effect=AssertionError("must refuse before SQLite opens"),
            ):
                result = inspect_offline_replacement_dependencies(alias)
            self.assertEqual(result["status"], "UNVERIFIABLE")
            self.assertIn("hardlink_not_allowed", result["issues"])

    def test_cli_json_and_exit_codes(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--db", str(self.db)]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "NO_DEPENDENCIES_OBSERVED")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--db", str(self.db) + ".missing"]), 2)


if __name__ == "__main__":
    unittest.main()
