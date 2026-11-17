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

    def test_invalid_ancestor_with_embedded_nul_fails_closed(self):
        invalid = "invalid\\x00WorkPool/path.sqlite3".replace("\\x00", "\x00")
        report = audit_stage_sqlite(invalid)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("database_path_not_verifiable", report["issues"])

    def test_refuses_workpool_ancestors_before_opening_db(self):
        import shutil
        original = self.valid_database()
        for folder in ("WorkPool", "workpool-archive"):
            with self.subTest(folder=folder):
                blocked = Path(self.tmp.name) / folder
                blocked.mkdir()
                db_copy = blocked / "offline.sqlite3"
                shutil.copyfile(original, db_copy)
                original_bytes = db_copy.read_bytes()
                result = audit_stage_sqlite(db_copy)
                self.assertEqual(result["status"], "FAIL")
                self.assertEqual(result["issues"], ["workpool_path_not_allowed"])
                self.assertEqual(db_copy.read_bytes(), original_bytes)

    def test_workpool_parent_symlink_alias_fails_closed(self):
        import shutil
        original = self.valid_database()
        blocked = Path(self.tmp.name) / "WorkPool-original"
        blocked.mkdir()
        shutil.copyfile(original, blocked / "offline.sqlite3")
        alias = Path(self.tmp.name) / "alias-parent"
        try:
            alias.symlink_to(blocked, target_is_directory=True)
        except (OSError, NotImplementedError):
            return  # Windows symlinks may need elevated privilege.
        result = audit_stage_sqlite(alias / "offline.sqlite3")
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("workpool_path_not_allowed", result["issues"])

    def test_hardlinked_offline_alias_is_refused_before_sqlite_open(self):
        import os
        path = self.valid_database()
        alias = Path(self.tmp.name) / "second-hardlink.sqlite3"
        try:
            os.link(path, alias)
        except (OSError, NotImplementedError):
            self.skipTest("Hard-link creation not supported on this filesystem")
        before = path.read_bytes()
        for candidate in (path, alias):
            with self.subTest(candidate=candidate):
                result = audit_stage_sqlite(candidate)
                self.assertEqual(result["status"], "FAIL")
                self.assertIn("hardlink_not_allowed", result["issues"])
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(alias.read_bytes(), before)

    def test_file_change_between_precheck_and_sqlite_open_fails_closed(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_audit as mod
        path = self.valid_database()
        uri = mod._readonly_uri
        before = path.read_bytes()
        called = 0
        def change_copy_before_open(candidate):
            nonlocal called
            called += 1
            with closing(sqlite3.connect(candidate)) as db:
                db.execute('CREATE TABLE "unrelated_added" ("x" TEXT)')
                db.commit()
            return uri(candidate)
        with patch.object(mod, "_readonly_uri",
                          side_effect=change_copy_before_open):
            report = audit_stage_sqlite(path)
        self.assertEqual(called, 1)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("offline_copy_changed_during_audit", report["issues"])
        self.assertNotEqual(path.read_bytes(), before)

    def test_sidecar_created_during_schema_scan_is_never_audit_pass(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_audit as mod
        path = self.valid_database()
        sidecar = Path(str(path) + "-wal")
        uri = mod._readonly_uri
        def add_sidecar(candidate):
            sidecar.write_bytes(b"fake-pending-log")
            return uri(candidate)
        with patch.object(mod, "_readonly_uri", side_effect=add_sidecar):
            report = audit_stage_sqlite(path)
        self.assertEqual(report["status"], "FAIL")
        self.assertIn("offline_copy_changed_during_audit", report["issues"])
        self.assertEqual(sidecar.read_bytes(), b"fake-pending-log")

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
