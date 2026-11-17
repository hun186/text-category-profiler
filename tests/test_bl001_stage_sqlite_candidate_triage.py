"""Private offline candidate triage guards and no-mutation tests."""
from contextlib import closing, redirect_stdout
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scripts.bl001_stage_sqlite_candidate_triage import triage_offline_copy, main


class OfflineCandidateTriageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ki012-offline-triage-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "offline.sqlite3"
        with closing(sqlite3.connect(self.path)) as cnx:
            cnx.execute('CREATE TABLE "sampleSrc" ("index" INT, "text" TEXT)')
            cnx.execute('CREATE INDEX "text_Index" ON "sampleSrc"("text")')
            cnx.commit()

    def _create_candidate(self, suffix, text_field=True, pandas_index=True):
        name = "__bl001_stage_" + suffix
        with closing(sqlite3.connect(self.path)) as cnx:
            cnx.execute(
                'CREATE TABLE "' + name + '" (' +
                ('"index" INT, "text" TEXT)' if text_field else '"index" INT)')
            )
            if pandas_index:
                cnx.execute('CREATE INDEX "ix_' + name +
                            '_index" ON "' + name + '"("index")')
            cnx.commit()
        return name

    def test_no_candidates_is_readonly_clear_not_cleanup(self):
        before = self.path.read_bytes()
        status = triage_offline_copy(self.path)
        self.assertEqual(status["status"], "PASS_NO_CANDIDATES")
        self.assertEqual(status["candidate_count"], 0)
        self.assertFalse(status["deletion_authorized"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_valid_candidate_is_still_manual_review_and_never_safe_to_delete(self):
        candidate = self._create_candidate("a" * 32)
        before = self.path.read_bytes()
        report = triage_offline_copy(self.path)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["candidates"][0]["table"], candidate)
        self.assertTrue(report["candidates"][0]["has_text_column"])
        self.assertTrue(report["candidates"][0]["has_pandas_index"])
        self.assertFalse(report["candidates"][0]["safe_to_delete"])
        self.assertEqual(report["owner_status"], "UNKNOWN")
        self.assertEqual(self.path.read_bytes(), before)

    def test_structurally_malformed_candidate_is_detected_without_deletion(self):
        self._create_candidate("b" * 32, text_field=False, pandas_index=False)
        report = triage_offline_copy(self.path)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertFalse(report["candidates"][0]["has_text_column"])
        self.assertFalse(report["candidates"][0]["has_pandas_index"])
        self.assertFalse(report["deletion_authorized"])

    def test_unique_pandas_named_index_is_invalid(self):
        candidate = self._create_candidate("d" * 32, pandas_index=False)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE UNIQUE INDEX "ix_' + candidate
                       + '_index" ON "' + candidate + '" ("index")')
            db.commit()
        before = self.path.read_bytes()
        rec = triage_offline_copy(self.path)["candidates"][0]
        self.assertFalse(rec["has_pandas_index"])
        self.assertEqual(rec["invalid_pandas_index_count"], 1)
        self.assertFalse(rec["all_indexes_pandas_compatible"])
        self.assertFalse(rec["safe_to_delete"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_pandas_prefix_impostor_index_is_not_compatible(self):
        candidate = self._create_candidate("f" * 32, pandas_index=False)
        manual = "ix_" + candidate + "_manual_search"
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE INDEX "' + manual
                       + '" ON "' + candidate + '" ("index")')
            db.commit()
        before = self.path.read_bytes()
        report = triage_offline_copy(self.path)
        record = report["candidates"][0]
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(record["invalid_pandas_index_count"], 1)
        self.assertEqual(record["invalid_pandas_index_names"], [manual])
        self.assertFalse(record["has_pandas_index"])
        self.assertFalse(record["all_indexes_pandas_compatible"])
        self.assertFalse(record["safe_to_delete"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_mixed_valid_wrong_collation_and_unexpected_index(self):
        candidate = self._create_candidate("e" * 32)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE INDEX "ix_' + candidate
                       + '_text" ON "' + candidate + '" ("text" COLLATE NOCASE)')
            db.execute('CREATE INDEX "unexpected_index" ON "'
                       + candidate + '" ("text")')
            db.commit()
        before = self.path.read_bytes()
        result = triage_offline_copy(self.path)
        rec = result["candidates"][0]
        self.assertTrue(rec["has_pandas_index"])
        self.assertEqual(rec["invalid_pandas_index_count"], 1)
        self.assertEqual(rec["unexpected_index_count"], 1)
        self.assertEqual(rec["all_index_count"], 3)
        self.assertFalse(rec["all_indexes_pandas_compatible"])
        self.assertEqual(result["owner_status"], "UNKNOWN")
        self.assertFalse(result["deletion_authorized"])
        self.assertEqual(self.path.read_bytes(), before)

    def test_real_pandas_named_and_multiindex_are_recognized(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("pandas not available")
        cases = (
            pd.Index(["甲"], name="uid"),
            pd.MultiIndex.from_tuples([("A", 3)], names=["group", "unit"]),
        )
        for i, index in enumerate(cases, 1):
            name = "__bl001_stage_" + format(i, "032x")
            frame = pd.DataFrame({"text": ["中文"]}, index=index)
            with closing(sqlite3.connect(self.path)) as cnx:
                frame.to_sql(name=name, con=cnx, if_exists="fail")
            record = next(
                x for x in triage_offline_copy(self.path)["candidates"]
                if x["table"] == name
            )
            self.assertTrue(record["has_pandas_index"], record)
            self.assertTrue(record["pandas_index_names"])
            self.assertTrue(record["all_indexes_pandas_compatible"])

    def test_case_variant_prefix_is_reported_as_suspicious(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE "__BL001_STAGE_'
                       + "a" * 32 + '" ("text" TEXT)')
            db.commit()
        report = triage_offline_copy(self.path)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["unexpected_prefix_count"], 1)
        self.assertEqual(report["owner_status"], "UNKNOWN")
        self.assertFalse(report["deletion_authorized"])

    def test_malformed_prefix_total_not_lost_when_name_list_is_capped(self):
        with closing(sqlite3.connect(self.path)) as db:
            for n in range(23):
                db.execute(
                    'CREATE TABLE "__bl001_stage_unexpected_' + str(n) + '" ("text" TEXT)'
                )
            db.commit()
        original = self.path.read_bytes()
        report = triage_offline_copy(self.path)
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["unexpected_prefix_count"], 23)
        self.assertEqual(report["unexpected_prefix_count_known"], 20)
        self.assertTrue(report["unexpected_prefix_names_truncated"])
        self.assertFalse(report["deletion_authorized"])
        self.assertEqual(report["owner_status"], "UNKNOWN")
        self.assertEqual(original, self.path.read_bytes())

    def test_workpool_ancestor_and_missing_db_refused(self):
        pool = Path(self.tmp.name) / "WorkPool"
        pool.mkdir()
        import shutil
        shutil.copyfile(self.path, pool / "a.sqlite3")
        self.assertEqual(triage_offline_copy(pool / "a.sqlite3")["status"],
                         "UNVERIFIABLE")
        self.assertEqual(triage_offline_copy(pool / "missing.sqlite3")["status"],
                         "UNVERIFIABLE")

    def test_new_candidate_after_clear_inventory_is_not_false_pass(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_candidate_triage as mod
        original = mod.inventory_offline_copy
        def change_after_inventory(path):
            summary = original(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute(
                    'CREATE TABLE "__bl001_stage_'
                    + "f" * 32 + '" ("text" TEXT)'
                )
                db.commit()
            return summary
        with patch.object(mod, "inventory_offline_copy",
                          side_effect=change_after_inventory):
            report = triage_offline_copy(self.path)
        self.assertEqual(report["status"], "UNVERIFIABLE")
        self.assertIn("candidate_schema_changed_since_inventory", report["issues"])
        self.assertEqual(report["candidates"], [])
        self.assertFalse(report["deletion_authorized"])

    def test_equal_count_rename_after_inventory_is_not_false_triage(self):
        from unittest.mock import patch
        from scripts import bl001_stage_sqlite_candidate_triage as mod
        old_name = self._create_candidate("a" * 32)
        original = mod.inventory_offline_copy
        def change_after_inventory(path):
            summary = original(path)
            with closing(sqlite3.connect(path)) as db:
                db.execute(
                    'ALTER TABLE "' + old_name + '" RENAME TO "'
                    + "__bl001_stage_" + "e" * 32 + '"'
                )
                db.commit()
            return summary
        with patch.object(mod, "inventory_offline_copy",
                          side_effect=change_after_inventory):
            result = triage_offline_copy(self.path)
        self.assertEqual(result["status"], "UNVERIFIABLE")
        self.assertIn("candidate_schema_changed_since_inventory", result["issues"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["owner_status"], "UNKNOWN")
        self.assertFalse(result["deletion_authorized"])

    def test_cli_status_codes_distinguish_review_and_missing_db(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--db", str(self.path)]), 0)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "PASS_NO_CANDIDATES")
        self._create_candidate("c" * 32)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--db", str(self.path)]), 1)
        self.assertEqual(json.loads(out.getvalue())["status"],
                         "REVIEW_REQUIRED")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--db", str(Path(self.tmp.name) / "missing")]), 2)
        self.assertEqual(json.loads(out.getvalue())["status"], "UNVERIFIABLE")


if __name__ == "__main__":
    unittest.main()
