"""Metadata-only WorkPool safety characterization using disposable fixtures."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.bl001_workpool_readonly_inventory import (
    inventory_workpool_metadata, main,
)


class WorkPoolMetadataInventoryTests(unittest.TestCase):
    def test_observes_workspace_states_and_database_metadata_without_opening_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "WorkPool"
            running = root / "dataset_1_is_running_RunClassfier"
            ready = root / "dataset_2_rdy_for_Spike"
            other = root / "dataset_3_ready"
            for directory in (running, ready, other):
                directory.mkdir(parents=True)
            (ready / "test.sql3").write_bytes(b"fake db, never parse")
            (ready / "test.sql3-wal").write_bytes(b"fake wal, never parse")
            (ready / "test.tsv").write_text("sensitive contents", encoding="utf-8")
            before = {p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                      for p in root.rglob("*") if p.is_file()}
            with mock.patch("builtins.open", side_effect=AssertionError(
                "inventory must never open a file"
            )), mock.patch("sqlite3.connect", side_effect=AssertionError(
                "inventory must never open SQLite"
            )):
                result = inventory_workpool_metadata(root)
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            self.assertEqual(result["workspace_running"], 1)
            self.assertEqual(result["workspace_ready"], 1)
            self.assertEqual(result["workspace_other"], 1)
            self.assertEqual(result["sqlite_files_observed"], 1)
            self.assertEqual(result["sqlite_sidecars_observed"], 1)
            self.assertEqual(result["sqlite_file_bytes_observed"], len(b"fake db, never parse"))
            self.assertEqual(result["file_contents_read"], False)
            self.assertFalse(result["sqlite_connections_opened"])
            self.assertFalse(result["production_workpool_verified"])
            self.assertFalse(result["deployment_authorized"])
            self.assertIn("running_workspaces_observed", result["issues"])
            self.assertIn("sqlite_sidecars_observed", result["issues"])
            self.assertNotIn("sensitive contents", json.dumps(result))
            self.assertNotIn("dataset_1", json.dumps(result))
            after = {p.relative_to(root).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns)
                     for p in root.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_quiet_inventory_does_not_claim_production_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "WorkPool"
            (root / "dataset_rdy_for_Spike").mkdir(parents=True)
            report = inventory_workpool_metadata(root)
            self.assertEqual(report["status"], "OBSERVED_METADATA_ONLY")
            self.assertEqual(report["workspace_ready"], 1)
            self.assertEqual(report["issues"], [])
            self.assertFalse(report["production_workpool_verified"])
            self.assertFalse(report["deployment_authorized"])
            self.assertFalse(report["candidate_deletion_authorized"])

    def test_root_name_missing_or_file_are_unverifiable(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "WorkPool"
            self.assertIn("root_unavailable", inventory_workpool_metadata(root)["issues"])
            (base / "not-a-pool").mkdir()
            self.assertIn("root_name_not_workpool",
                          inventory_workpool_metadata(base / "not-a-pool")["issues"])
            root.write_text("not a dir", encoding="utf-8")
            self.assertIn("root_not_directory", inventory_workpool_metadata(root)["issues"])

    def test_entry_budget_fails_closed_with_no_ready_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "WorkPool"
            root.mkdir()
            for number in range(5):
                (root / f"dataset_{number}.sql3").write_bytes(b"X")
            report = inventory_workpool_metadata(root, max_entries=2)
            self.assertEqual(report["status"], "UNVERIFIABLE")
            self.assertIn("entry_budget_exhausted", report["issues"])
            self.assertFalse(report["deployment_authorized"])

    def test_max_depth_bounds_traversal_and_declares_unscanned_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "WorkPool"
            deep = root / "dataset_0_rdy_for_Spike" / "logs"
            deep.mkdir(parents=True)
            (deep / "hidden.sql3-wal").write_bytes(b"hidden")
            report = inventory_workpool_metadata(root, max_depth=1)
            self.assertEqual(report["directories_not_descended"], 1)
            self.assertEqual(report["sqlite_sidecars_observed"], 0)
            self.assertEqual(report["status"], "OBSERVED_METADATA_ONLY")
            self.assertFalse(report["production_workpool_verified"])

    def test_reparse_entries_not_followed(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "WorkPool"
            root.mkdir()
            target = base / "external"
            target.mkdir()
            (target / "secret.sql3-wal").write_bytes(b"outside")
            linked = root / "external-link"
            try:
                linked.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privilege not available")
            report = inventory_workpool_metadata(root)
            self.assertEqual(report["status"], "REVIEW_REQUIRED")
            self.assertEqual(report["reparse_entries_observed"], 1)
            self.assertEqual(report["sqlite_sidecars_observed"], 0)

    def test_root_symlink_is_rejected_before_scan(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            target = base / "source"
            target.mkdir()
            alias = base / "WorkPool"
            try:
                alias.symlink_to(target, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privilege not available")
            with mock.patch("scripts.bl001_workpool_readonly_inventory.os.scandir",
                            side_effect=AssertionError("must not follow root alias")):
                report = inventory_workpool_metadata(alias)
            self.assertEqual(report["status"], "UNVERIFIABLE")
            self.assertIn("path_reparse_point_not_allowed", report["issues"])

    def test_cli_nonpass_verdicts_and_parameter_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "WorkPool"
            root.mkdir()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["--workpool", str(root)]), 0)
            record = json.loads(out.getvalue())
            self.assertEqual(record["status"], "OBSERVED_METADATA_ONLY")
            self.assertFalse(record["deployment_authorized"])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--workpool", str(root), "--max-depth", "9"]), 2)
                self.assertEqual(main(["--workpool", str(root / "absent")]), 2)

    def test_invalid_bounds_rejected_before_scan(self):
        with self.assertRaises(ValueError):
            inventory_workpool_metadata("WorkPool", max_entries=0)
        with self.assertRaises(ValueError):
            inventory_workpool_metadata("WorkPool", max_depth=5)


if __name__ == "__main__":
    unittest.main()
