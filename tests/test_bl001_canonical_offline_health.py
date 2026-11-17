"""Private, detached-copy Canonical SQLite health acceptance.

No WorkPool, model, external databases, or production state are touched.
"""
from contextlib import closing
from pathlib import Path
import json
import os
import shutil
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_candidate_inventory import inventory_offline_copy
from scripts.bl001_stage_sqlite_offline_health import offline_quick_check


class CanonicalOfflineHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bl001-canonical-offline-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "test.sql3"
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE "sampleSrc" ("index" INTEGER, "OutLabel" TEXT, "text" TEXT)')
            db.execute('INSERT INTO sampleSrc VALUES (0, "CN-Politics", "中文")')
            db.execute('CREATE INDEX "ix_sampleSrc_index" ON sampleSrc("index")')
            db.commit()

    def test_realistic_canonical_index_profile_and_immutable_health(self):
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        self.assertEqual(inventory_offline_copy(self.path)["status"], "UNVERIFIABLE")
        self.assertIn("missing_text_Index", inventory_offline_copy(self.path)["issues"])
        report = offline_quick_check(self.path, profile="canonical")
        self.assertEqual(report["status"], "PASS_OFFLINE_QUICK_CHECK")
        self.assertEqual(report["profile"], "canonical")
        self.assertEqual(report["quick_check"], "ok")
        self.assertEqual(report["foreign_key_check"], "ok")
        self.assertEqual(report["candidate_count"], 0)
        self.assertFalse(report["production_workpool_verified"])
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_no_text_column_is_not_certified(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('ALTER TABLE sampleSrc RENAME TO discarded')
            db.execute('CREATE TABLE sampleSrc ("OutLabel" TEXT)')
            db.commit()
        report = offline_quick_check(self.path, profile="canonical")
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("missing_text_column", report["issues"])
        self.assertEqual(report["quick_check"], "NOT_RUN")

    def test_foreign_key_violation_cannot_pass(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE parent (id INTEGER PRIMARY KEY)')
            db.execute('CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))')
            db.execute('INSERT INTO child VALUES (42)')
            db.commit()
        report = offline_quick_check(self.path, profile="canonical")
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("sqlite_foreign_key_violations", report["issues"])
        self.assertEqual(report["foreign_key_check"], "FAIL")

    def test_candidate_and_invalid_name_never_authorize_cleanup(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE "__bl001_stage_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" (text TEXT)')
            db.execute('CREATE TABLE "__BL001_STAGE_odd" (text TEXT)')
            db.commit()
        report = offline_quick_check(self.path, profile="canonical")
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["candidate_count"], 1)
        self.assertEqual(report["unexpected_prefix_count"], 1)
        self.assertFalse(report["candidate_deletion_authorized"])

    def test_workpool_and_sidecar_refused_without_scan(self):
        root = Path(self.tmp.name) / "WorkPool-history"
        root.mkdir()
        blocked = root / "test.sql3"
        shutil.copyfile(self.path, blocked)
        report = offline_quick_check(blocked, profile="canonical")
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("workpool_path_not_allowed", report["issues"])
        sidecar = Path(str(self.path) + "-wal")
        sidecar.write_bytes(b"held WAL")
        self.assertIn("sqlite_journal_or_wal_present",
                      offline_quick_check(self.path, profile="canonical")["issues"])

    def test_hardlink_is_not_detached_copy(self):
        alias = Path(self.tmp.name) / "alias.sql3"
        try:
            os.link(self.path, alias)
        except (OSError, NotImplementedError):
            self.skipTest("Hard links unavailable")
        self.assertIn("hardlink_not_allowed",
                      offline_quick_check(self.path, profile="canonical")["issues"])

    def test_unrelated_database_not_silently_accepted(self):
        path = Path(self.tmp.name) / "other.sql3"
        with closing(sqlite3.connect(path)) as db:
            db.execute('CREATE TABLE "different" (text TEXT)')
            db.commit()
        report = offline_quick_check(path, profile="canonical")
        self.assertIn("missing_sampleSrc_table", report["issues"])

    def test_invalid_profile_rejected(self):
        with self.assertRaises(ValueError):
            offline_quick_check(self.path, profile="auto")
        with self.assertRaises(ValueError):
            inventory_offline_copy(self.path, profile="auto")


if __name__ == "__main__":
    unittest.main()
