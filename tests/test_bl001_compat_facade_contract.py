"""BL-001 legacy shims are bounded compatibility shells, not new code homes."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from scripts.bl001_compat_facade_contract import (
    ALLOWED_FACADE_FUNCTIONS, ROOT, audit, inspect_facade, main,
)


class CompatFacadeContractTests(unittest.TestCase):
    def test_all_eight_preserved_facades_have_explicit_stable_pure_ast_policy(self):
        report = audit(ROOT)
        self.assertEqual(report["issues"], [])
        self.assertEqual(report["status"], "PASS_FACADE_BOUNDARIES")
        self.assertEqual(len(report["compat_facades"]), 8)
        self.assertEqual(
            {row["legacy_path"] for row in report["compat_facades"]},
            set(ALLOWED_FACADE_FUNCTIONS),
        )
        self.assertTrue(all(row["external_callers"] == "UNVERIFIED"
                            for row in report["compat_facades"]))

    def test_pass_does_not_approve_removal_or_claim_external_resolution(self):
        report = audit(ROOT)
        self.assertIs(report["facade_removal_authorized"], False)
        self.assertIs(report["external_callers_verified"], False)
        self.assertIs(report["runtime_verified"], False)
        self.assertIn("not prove behavior", report["limitations"])

    def test_extra_business_definition_is_rejected(self):
        code = 'def main():\n    return None\n\ndef expensive_operation():\n    return 1\n'
        problems = inspect_facade(code, {"main"})
        self.assertIn("nonfacade_definitions:expensive_operation", problems)

    def test_class_implementation_is_rejected_even_when_named_as_allowed(self):
        problems = inspect_facade("class main:\n    pass\n", {"main"})
        self.assertIn("new_class_or_business_logic", problems)

    def test_deleted_existing_entrypoint_is_rejected(self):
        problems = inspect_facade("def __getattr__(name):\n    return name\n",
                                  {"__getattr__", "main"})
        self.assertIn("missing_legacy_compat_api:main", problems)

    def test_new_heavy_import_and_legacy_path_mutation_are_rejected(self):
        source = (
            "import requests\n"
            "import sys\n"
            "import os\n"
            "sys.path.insert(0, '/private/path')\n"
            "os.chdir('/tmp')\n"
        )
        problems = inspect_facade(source, set())
        self.assertIn("unreviewed_import:requests", problems)
        self.assertIn("unreviewed_import:sys", problems)
        self.assertIn("unreviewed_import:os", problems)
        self.assertIn("legacy_sys_path_mutation", problems)
        self.assertIn("legacy_chdir", problems)

    def test_current_allowed_lazy_provider_imports_remain_accepted(self):
        self.assertEqual(inspect_facade(
            "from pathlib import Path\n"
            "from importlib import import_module\n"
            "def __getattr__(name):\n"
            "    from experiments import rand_corpus_labeling\n"
            "    return rand_corpus_labeling\n"
            "def main():\n"
            "    return None\n",
            {"__getattr__", "main"},
        ), [])

    def test_report_is_machine_readable_and_never_claims_runtime_proof(self):
        with TemporaryDirectory() as tmp:
            destination = Path(tmp) / "facade-policy.json"
            self.assertEqual(main(["--output", str(destination)]), 0)
            output = json.loads(destination.read_text(encoding="utf-8"))
            self.assertIs(output["facade_removal_authorized"], False)
            self.assertEqual(output["issues"], [])

    def test_fail_gate_emits_nonzero_and_preserves_issue(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "blocked.json"
            fake = {
                "status": "BLOCKED_FACADE_BOUNDARIES",
                "issues": ["unexpected entrypoint implementation"],
            }
            with mock.patch("scripts.bl001_compat_facade_contract.audit",
                            return_value=fake):
                self.assertEqual(main(["--output", str(path)]), 1)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")),
                             fake)

    def test_no_legacy_module_is_imported_to_check_its_contract(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("no networking")):
            report = audit(ROOT)
        self.assertEqual(report["issues"], [])


if __name__ == "__main__":
    unittest.main()
