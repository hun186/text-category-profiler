"""BL-001 closure-readiness gate, without pretending to certify deployment."""
import ast
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.bl001_package_census import audit_package
from scripts.bl001_structural_readiness import (
    CONTRACTS, EXTERNAL_ACCEPTANCE, ROOT, audit, check_boundary,
    inspect_module, main,
)


class StructuralReadinessTests(unittest.TestCase):
    def test_current_main_has_static_stage_and_package_seams(self):
        report = audit(ROOT)
        self.assertEqual(report["status"],
                         "PASS_STRUCTURAL_BOUNDARIES_EXTERNAL_GATES_PENDING")
        self.assertEqual(report["issues"], [])
        self.assertEqual(
            report["structural_evidence"]["covered_boundary_modules"],
            len(CONTRACTS),
        )
        census = audit_package(ROOT)
        self.assertEqual(report["structural_evidence"]["tracked_package_files"],
                         census["summary"]["total_tracked_package_files"])
        self.assertEqual(report["structural_evidence"]["domain_owned"],
                         census["summary"]["canonical_domain_owned"])
        self.assertEqual(report["structural_evidence"]["legacy_compatibility_and_assets"],
                         census["summary"]["legacy_preserved"])

    def test_external_production_gates_can_never_be_inferred_from_ast(self):
        report = audit(ROOT)
        self.assertEqual(report["external_acceptance"], EXTERNAL_ACCEPTANCE)
        self.assertTrue(all(value == "UNVERIFIED" for value in
                            report["external_acceptance"].values()))
        for key in ("external_callers_verified", "production_workpool_verified",
                    "real_gui_verified", "model_gpu_verified",
                    "deployment_authorized", "bl001_formally_done"):
            self.assertIs(report[key], False)

    def test_boundary_inspection_rejects_missing_symbol_and_invalid_syntax(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "minimal.py"
            path.write_text("class Existing:\n    pass\n", encoding="utf-8")
            tree, failures = inspect_module(path, {"Existing", "Missing"})
            self.assertIsInstance(tree, ast.Module)
            self.assertEqual(failures, ["missing_symbol:Missing"])
            path.write_text("if :\n", encoding="utf-8")
            self.assertEqual(inspect_module(path, {"Existing"})[1],
                             ["module_not_parseable:SyntaxError"])
            path.unlink()
            self.assertEqual(inspect_module(path, set())[1],
                             ["module_not_parseable:FileNotFoundError"])

    def test_census_unknown_and_bad_identity_cannot_be_reported_ready(self):
        baseline = audit_package(ROOT)
        for key in ("unclassified_paths", "catalogue_paths_missing",
                    "invalid_catalog_entries", "identity_failures"):
            with self.subTest(field=key):
                report = copy.deepcopy(baseline)
                report[key] = ["unreviewed"]
                result = check_boundary(ROOT, report)
                self.assertIn("package_inventory:" + key, result["issues"])
                self.assertEqual(result["status"],
                                 "BLOCKED_STRUCTURAL_BOUNDARIES")
                self.assertFalse(result["deployment_authorized"])

    def test_census_with_false_authoritative_status_is_rejected(self):
        report = copy.deepcopy(audit_package(ROOT))
        report["external_callers_verified"] = True
        result = check_boundary(ROOT, report)
        self.assertIn("package_inventory:external_caller_status_changed",
                      result["issues"])
        self.assertFalse(result["bl001_formally_done"])

    def test_gate_report_writes_machine_readable_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "result.json"
            self.assertEqual(main(["--output", str(destination)]), 0)
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["issues"], [])
            self.assertIs(payload["deployment_authorized"], False)

    def test_failed_gate_writes_fail_status_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / "fail.json"
            with mock.patch(
                "scripts.bl001_structural_readiness.audit",
                return_value={"status": "BLOCKED_STRUCTURAL_BOUNDARIES",
                              "issues": ["synthetic regression"]},
            ):
                self.assertEqual(main(["--output", str(destination)]), 1)
            payload = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(payload["issues"], ["synthetic regression"])

    def test_audit_does_not_connect_to_network_or_load_stage_modules(self):
        with mock.patch("socket.socket", side_effect=AssertionError("network forbidden")):
            report = audit(ROOT)
        self.assertEqual(report["issues"], [])


if __name__ == "__main__":
    unittest.main()
