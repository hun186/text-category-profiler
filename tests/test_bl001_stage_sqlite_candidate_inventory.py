"""Private SQLite tests of fail-closed, read-only candidate metadata inventory."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_candidate_inventory import inventory_offline_copy, main


class CandidateInventoryTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix="ki012-candidate-inventory-")
        self.addCleanup(self.private.cleanup)
        self.db = Path(self.private.name) / "offline-copy.sqlite3"
        with closing(sqlite3.connect(self.db)) as cnx:
            cnx.execute('CREATE TABLE "sampleSrc" ("index" INTEGER, "text" TEXT, "label" TEXT)')
            cnx.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text")')
            cnx.commit()
        self.original = self.db.read_bytes()

    def _add_table(self, name):
        with closing(sqlite3.connect(self.db)) as cnx:
            cnx.execute('CREATE TABLE "' + name.replace('"', '""') + '" (sample TEXT)')
            cnx.commit()

    def test_clean_private_copy_reports_no_candidates_without_mutation(self):
        result = inventory_offline_copy(self.db)
        self.assertEqual(result["status"], "PASS_NO_CANDIDATES")
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["schema_status"], "PASS")
        self.assertEqual(result["scope"], "offline_quiescent_copy_readonly")
        self.assertEqual(self.db.read_bytes(), self.original)

    def test_candidate_presence_requires_review_without_row_scans_or_cleanup(self):
        candidate = "__bl001_stage_" + "a" * 32
        self._add_table(candidate)
        before = self.db.read_bytes()
        result = inventory_offline_copy(self.db)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidate_names"], [candidate])
        self.assertEqual(result["schema_status"], "PASS")
        self.assertEqual(self.db.read_bytes(), before)
        with closing(sqlite3.connect(self.db)) as cnx:
            self.assertIsNotNone(cnx.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (candidate,),
            ).fetchone())

    def test_unexpected_prefix_is_not_mistaken_for_owned_or_safe_candidate(self):
        self._add_table("__bl001_stage_invalid")
        report = inventory_offline_copy(self.db)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["unexpected_prefixed_names"], ["__bl001_stage_invalid"])

    def test_no_unbounded_table_name_output(self):
        for i in range(23):
            self._add_table("__bl001_stage_" + format(i, "032x"))
        result = inventory_offline_copy(self.db)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["candidate_count"], 23)
        self.assertEqual(len(result["candidate_names"]), 20)
        self.assertTrue(result["candidate_names_truncated"])

    def test_sidecars_and_missing_schema_fail_closed(self):
        sidecar = Path(str(self.db) + "-wal")
        sidecar.write_bytes(b"fake")
        self.assertEqual(inventory_offline_copy(self.db)["status"], "UNVERIFIABLE")
        self.assertIn("sqlite_journal_or_wal_present",
                      inventory_offline_copy(self.db)["issues"])
        sidecar.unlink()
        with closing(sqlite3.connect(self.db)) as cnx:
            cnx.execute('DROP INDEX "text_Index"')
            cnx.commit()
        result = inventory_offline_copy(self.db)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("main_stage_schema_not_verified", result["issues"])

    def test_invalid_missing_and_symlink_are_not_treated_as_clear(self):
        missing = Path(self.private.name) / "missing.sqlite3"
        self.assertEqual(inventory_offline_copy(missing)["status"], "UNVERIFIABLE")
        invalid = Path(self.private.name) / "not-sqlite.sqlite3"
        invalid.write_bytes(b"X" * 1024)
        self.assertEqual(inventory_offline_copy(invalid)["status"], "UNVERIFIABLE")
        link = Path(self.private.name) / "link.sqlite3"
        try:
            link.symlink_to(self.db)
        except (NotImplementedError, OSError):
            return  # Windows may require special privileges for symlinks
        self.assertIn("symlink_not_allowed", inventory_offline_copy(link)["issues"])

    def test_live_workpool_spelling_is_rejected_even_for_valid_database(self):
        import shutil
        pool = Path(self.private.name) / "WorkPool"
        pool.mkdir()
        live = pool / "active.sqlite3"
        shutil.copyfile(self.db, live)
        before = live.read_bytes()
        result = inventory_offline_copy(live)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("workpool_path_not_allowed", result["issues"])
        self.assertEqual(live.read_bytes(), before)

        # A standalone off-line copy may itself be named WorkPool-*.sqlite3.
        standalone = Path(self.private.name) / "WorkPool-offline.sqlite3"
        shutil.copyfile(self.db, standalone)
        self.assertEqual(inventory_offline_copy(standalone)["status"],
                         "PASS_NO_CANDIDATES")

        parent = Path(self.private.name) / "workpool-backups"
        parent.mkdir()
        shutil.copyfile(self.db, parent / "copy.sqlite3")
        self.assertIn(
            "workpool_path_not_allowed",
            inventory_offline_copy(parent / "copy.sqlite3")["issues"],
        )

    def test_cli_exit_codes_are_distinct_and_report_json(self):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--db", str(self.db)])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "PASS_NO_CANDIDATES")
        self._add_table("__bl001_stage_" + "b" * 32)
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--db", str(self.db)])
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "REVIEW_REQUIRED")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = main(["--db", str(Path(self.private.name) / "missing.sqlite3")])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "UNVERIFIABLE")


if __name__ == "__main__":
    unittest.main()
