"""Dependency-light, private-disk tests for the BL-001 read-only SQLite audit."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_audit import audit_stage_sqlite, main


class StageSQLiteAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bl001-sqlite-audit-")
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "中文 stage.sqlite3"

    def database(self, *sql):
        with closing(sqlite3.connect(self.db_path)) as db:
            for statement in sql:
                db.execute(statement)
            db.commit()
        return self.db_path

    def valid_database(self):
        return self.database(
            'CREATE TABLE "sampleSrc" ("text" TEXT, "label" TEXT)',
            'INSERT INTO "sampleSrc" VALUES ("樣本", "TW Affairs")',
            'CREATE INDEX "text_Index" ON "sampleSrc" ("text")',
        )

    def test_valid_index_is_actual_text_column_and_audit_does_not_mutate_file(self):
        path = self.valid_database()
        initial = (path.read_bytes(), path.stat().st_mtime_ns)
        report = audit_stage_sqlite(path)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["columns"], ["text", "label"])
        self.assertEqual(report["index_key_columns"], ["text"])
        self.assertEqual(report["index_properties"], {
            "unique": False, "origin": "c", "partial": False,
        })
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), initial)
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse(Path(str(path) + suffix).exists())

    def test_missing_text_is_detected_even_when_expression_index_exists(self):
        self.database(
            'CREATE TABLE "sampleSrc" ("label" TEXT)',
            'CREATE INDEX "text_Index" ON "sampleSrc" ((label || "suffix"))',
        )
        report = audit_stage_sqlite(self.db_path)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("missing_text_column", report["issues"])
        self.assertIn("text_Index_not_bound_to_text_column", report["issues"])
        self.assertEqual(report["index_key_columns"], [None])

    def test_missing_and_wrong_indexes_are_reported(self):
        self.database('CREATE TABLE "sampleSrc" ("text" TEXT)')
        self.assertIn("missing_text_Index", audit_stage_sqlite(self.db_path)["issues"])
        with closing(sqlite3.connect(self.db_path)) as db:
            db.execute('CREATE TABLE "other" ("text" TEXT)')
            db.execute('CREATE INDEX "text_Index" ON "other" ("text")')
            db.commit()
        self.assertIn(
            "text_Index_on_wrong_table", audit_stage_sqlite(self.db_path)["issues"]
        )

    def test_multi_column_key_is_not_the_fixed_stage_contract(self):
        self.database(
            'CREATE TABLE "sampleSrc" ("text" TEXT, "label" TEXT)',
            'CREATE INDEX "text_Index" ON "sampleSrc" ("text", "label")',
        )
        report = audit_stage_sqlite(self.db_path)
        self.assertEqual(report["index_key_columns"], ["text", "label"])
        self.assertIn("text_Index_not_bound_to_text_column", report["issues"])

    def test_unique_partial_desc_and_nocase_indexes_fail_closed(self):
        # All four variants have a single real text key and previously
        # passed index_xinfo-only validation despite different semantics.
        variants = (
            ("unique", 'CREATE UNIQUE INDEX "text_Index" ON "sampleSrc" ("text")',
             "text_Index_not_plain_nonunique_full"),
            ("partial", 'CREATE INDEX "text_Index" ON "sampleSrc" ("text") WHERE "label" IS NOT NULL',
             "text_Index_not_plain_nonunique_full"),
            ("descending", 'CREATE INDEX "text_Index" ON "sampleSrc" ("text" DESC)',
             "text_Index_wrong_order_or_collation"),
            ("nocase", 'CREATE INDEX "text_Index" ON "sampleSrc" ("text" COLLATE NOCASE)',
             "text_Index_wrong_order_or_collation"),
        )
        for label, ddl, reason in variants:
            with self.subTest(index_variant=label):
                if self.db_path.exists():
                    self.db_path.unlink()
                path = self.database(
                    'CREATE TABLE "sampleSrc" ("text" TEXT, "label" TEXT)',
                    ddl,
                )
                original = (path.read_bytes(), path.stat().st_mtime_ns)
                result = audit_stage_sqlite(path)
                self.assertEqual(result["status"], "FAIL")
                self.assertIn(reason, result["issues"])
                self.assertEqual(result["index_key_columns"], ["text"])
                self.assertEqual(
                    (path.read_bytes(), path.stat().st_mtime_ns), original,
                    "Auditing an index must never mutate the SQLite copy",
                )

    def test_missing_table_is_fail_closed(self):
        self.database('CREATE TABLE "unrelated" ("text" TEXT)')
        report = audit_stage_sqlite(self.db_path)
        self.assertIn("missing_sampleSrc_table", report["issues"])
        self.assertIn("missing_text_Index", report["issues"])

    def test_nonexistent_path_does_not_create_database(self):
        report = audit_stage_sqlite(self.db_path)
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["issues"], ["database_not_found"])
        self.assertFalse(self.db_path.exists())

    def test_sidecar_fails_before_opening_and_preserves_bytes(self):
        path = self.valid_database()
        original = path.read_bytes()
        sidecar = Path(str(path) + "-wal")
        sidecar.write_bytes(b"simulated pending WAL")
        report = audit_stage_sqlite(path)
        self.assertEqual(report["issues"], ["sqlite_journal_or_wal_present"])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(sidecar.read_bytes(), b"simulated pending WAL")

    def test_corrupt_or_truncated_file_is_rejected(self):
        self.db_path.write_bytes(b"x" * 512)
        self.assertEqual(
            audit_stage_sqlite(self.db_path)["issues"],
            ["database_unreadable_or_invalid"],
        )
        self.db_path.write_bytes(b"")
        self.assertEqual(
            audit_stage_sqlite(self.db_path)["issues"],
            ["database_empty_or_truncated"],
        )

    def test_symlink_to_valid_database_is_rejected(self):
        path = self.valid_database()
        link = Path(self.tmp.name) / "shortcut.sqlite3"
        try:
            link.symlink_to(path)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation not supported")
        self.assertEqual(
            audit_stage_sqlite(link)["issues"], ["symlink_not_allowed"]
        )

    def test_cli_prints_machine_readable_json_and_status(self):
        path = self.valid_database()
        out = io.StringIO()
        with redirect_stdout(out):
            success = main(["--db", str(path)])
        self.assertEqual(success, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PASS")
        out = io.StringIO()
        with redirect_stdout(out):
            failure = main(["--db", str(path) + ".missing"])
        self.assertEqual(failure, 1)
        self.assertEqual(json.loads(out.getvalue())["issues"], ["database_not_found"])


if __name__ == "__main__":
    unittest.main()
