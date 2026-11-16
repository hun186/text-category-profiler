"""Private-disk tests for the bounded, immutable offline SQLite quick_check."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_offline_health import offline_quick_check, main


class OfflineHealthTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix="ki012-offline-health-")
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)
        self.path = self.root / "detached.sqlite3"
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE sampleSrc ("text" TEXT, "label" TEXT)')
            db.execute('INSERT INTO sampleSrc VALUES ("中文", "KEEP")')
            db.execute('CREATE INDEX "text_Index" ON sampleSrc("text")')
            db.commit()

    def test_valid_detached_copy_is_unchanged(self):
        before = (self.path.read_bytes(), self.path.stat().st_mtime_ns)
        r = offline_quick_check(self.path)
        self.assertEqual(r["status"], "PASS_OFFLINE_QUICK_CHECK")
        self.assertEqual(r["quick_check"], "ok")
        self.assertEqual(r["candidate_count"], 0)
        self.assertFalse(r["candidate_deletion_authorized"])
        self.assertFalse(r["production_workpool_verified"])
        self.assertEqual((self.path.read_bytes(), self.path.stat().st_mtime_ns), before)

    def test_candidates_are_not_declared_safe_even_with_healthy_quickcheck(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(
                'CREATE TABLE "__bl001_stage_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" '
                '("text" TEXT)'
            )
            db.commit()
        result = offline_quick_check(self.path)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["quick_check"], "ok")
        self.assertEqual(result["candidate_count"], 1)
        self.assertFalse(result["candidate_deletion_authorized"])

    def test_valid_foreign_key_is_checked_without_mutation(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE UNIQUE INDEX "unique_parent_text" '
                       'ON "sampleSrc"("text")')
            db.execute('CREATE TABLE "child" ('
                       '"ref" TEXT REFERENCES "sampleSrc"("text"))')
            db.execute('INSERT INTO "child" VALUES ("中文")')
            db.commit()
        before = self.path.read_bytes()
        result = offline_quick_check(self.path)
        self.assertEqual(result["status"], "PASS_OFFLINE_QUICK_CHECK")
        self.assertEqual(result["foreign_key_check"], "ok")
        self.assertEqual(self.path.read_bytes(), before)

    def test_broken_foreign_key_is_not_false_green_even_if_quick_check_ok(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE UNIQUE INDEX "unique_parent_text" '
                       'ON "sampleSrc"("text")')
            db.execute('CREATE TABLE "child" ('
                       '"ref" TEXT REFERENCES "sampleSrc"("text"))')
            # With SQLite's default foreign_keys=OFF, a broken reference can
            # exist on an otherwise page-integrity-clean detached DB.
            db.execute('INSERT INTO "child" VALUES ("missing-parent")')
            db.commit()
        before = self.path.read_bytes()
        result = offline_quick_check(self.path)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertEqual(result["quick_check"], "ok")
        self.assertEqual(result["foreign_key_check"], "FAIL")
        self.assertIn("sqlite_foreign_key_violations", result["issues"])
        self.assertNotIn("missing-parent", json.dumps(result))
        self.assertFalse(result["candidate_deletion_authorized"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_candidate_created_after_quickcheck_cannot_false_green(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_offline_health as mod
        original = mod.inventory_offline_copy
        count = 0
        def new_candidate_on_second_inventory(path):
            nonlocal count
            count += 1
            if count == 2:
                with closing(sqlite3.connect(path)) as db:
                    db.execute(
                        'CREATE TABLE "__bl001_stage_'
                        + "f" * 32 + '" ("text" TEXT)'
                    )
                    db.commit()
            return original(path)
        with patch.object(mod, "inventory_offline_copy",
                          side_effect=new_candidate_on_second_inventory):
            result = offline_quick_check(self.path)
        self.assertEqual(count, 2)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("offline_copy_changed_during_check", result["issues"])
        self.assertFalse(result["candidate_deletion_authorized"])
        self.assertFalse(result["production_workpool_verified"])

    def test_equal_count_candidate_rename_after_quickcheck_is_detected(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_offline_health as mod
        old = "__bl001_stage_" + "a" * 32
        new = "__bl001_stage_" + "b" * 32
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE "' + old + '" ("text" TEXT)')
            db.commit()
        original = mod.inventory_offline_copy
        count = 0
        def rename_on_second_inventory(path):
            nonlocal count
            count += 1
            if count == 2:
                with closing(sqlite3.connect(path)) as db:
                    db.execute(
                        'ALTER TABLE "' + old + '" RENAME TO "' + new + '"'
                    )
                    db.commit()
            return original(path)
        with patch.object(mod, "inventory_offline_copy",
                          side_effect=rename_on_second_inventory):
            result = offline_quick_check(self.path)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("offline_copy_changed_during_check", result["issues"])
        self.assertEqual(result["quick_check"], "ok")
        self.assertFalse(result["candidate_deletion_authorized"])

    def test_workpool_and_sidecar_are_refused_before_quickcheck(self):
        folder = self.root / "WorkPool-copy"
        folder.mkdir()
        other = folder / "db.sqlite3"
        shutil.copyfile(self.path, other)
        result = offline_quick_check(other)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("workpool_path_not_allowed", result["issues"])
        path_sidecar = Path(str(self.path) + "-wal")
        path_sidecar.write_bytes(b"fake")
        self.assertIn("sqlite_journal_or_wal_present",
                      offline_quick_check(self.path)["issues"])

    def test_size_cap_and_invalid_option_fail_closed(self):
        # The quota check must not scan a DB that is over a stated limit.
        # Avoid creating a 1 MiB fixture; inject metadata size for a valid DB.
        from unittest.mock import patch
        import os
        source_stat = self.path.stat()
        class OversizedStat:
            st_size = 2 * 1024 * 1024
            def __getattr__(self, key):
                return getattr(source_stat, key)
        fake = OversizedStat()
        original_stat = Path.stat
        def oversized(path, *args, **kwargs):
            if path == self.path:
                return fake
            return original_stat(path, *args, **kwargs)
        with patch.object(Path, "stat", oversized):
            report = offline_quick_check(self.path, max_mib=1)
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("offline_copy_exceeds_bounded_scan_limit", report["issues"])
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--db", str(self.path), "--max-mib", "4097"]), 2)
            self.assertEqual(main(["--db", str(self.path), "--max-mib", "0"]), 2)

    def test_cli_machine_status(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--db", str(self.path), "--max-mib", "1"])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "PASS_OFFLINE_QUICK_CHECK")


if __name__ == "__main__":
    unittest.main()
