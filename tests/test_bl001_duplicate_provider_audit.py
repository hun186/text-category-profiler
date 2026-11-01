"""Isolated, dependency-free regression of BL-001 duplicate-provider evidence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.bl001_duplicate_provider_audit import (
    FAMILIES, ROOT, _public_definitions, _source_imports, audit,
)


class DuplicateProviderEvidenceTests(unittest.TestCase):
    def test_three_real_families_remain_structurally_distinct(self):
        report = audit(ROOT, [])
        self.assertEqual(report["family_count"], 3)
        self.assertEqual(report["provider_count"], 9)
        self.assertFalse(report["runtime_verified"])
        self.assertFalse(report["external_callers_verified"])
        self.assertEqual([x["family"] for x in report["families"]],
                         ["df_utils", "MP_utils", "utilities"])
        for family in report["families"]:
            self.assertEqual(len(family["versions"]), 3)
            self.assertEqual(family["versions"][0]["role"], "package_domain_owner")
            self.assertFalse(family["safe_to_consolidate"])
            self.assertFalse(family["source_bytes_all_identical"])
            for row in family["versions"]:
                self.assertTrue(row["sha256"])
                self.assertGreater(row["byte_length"], 0)
                self.assertFalse(row["runtime_authority_verified"])
        self.assertIn(
            "dfOutputer",
            next(x for x in report["families"] if x["family"] == "df_utils")[
                "common_public_definitions"
            ],
        )

    def test_ast_comparison_and_scoped_import_matches_without_importing_targets(self):
        names = {
            "text_category_profiler.data.df_utils",
            "DatasetConverter.df_utils",
        }
        self.assertEqual(
            _source_imports(
                "from DatasetConverter import df_utils\n"
                "import text_category_profiler.data.df_utils\n"
                "x = 'DatasetConverter.df_utils'\n",
                names,
            ),
            names,
        )
        self.assertEqual(
            _source_imports("importlib.import_module('DatasetConverter.df_utils')\n", names),
            set(),
        )
        import ast
        parsed = ast.parse("def public(): pass\ndef _private(): pass\nclass Example: pass\n")
        self.assertEqual(set(_public_definitions(parsed)), {"public", "Example"})

    def test_missing_registered_provider_fails_closed(self):
        with TemporaryDirectory() as temp:
            with self.assertRaisesRegex(AssertionError, "provider source missing"):
                audit(Path(temp), [])

    def test_in_repository_explicit_callers_are_labeled_not_runtime_verified(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            for paths in FAMILIES.values():
                for path in paths:
                    dest = root / path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_text("def shared(): return 1\n", encoding="utf-8")
            caller = root / "TCFMain.py"
            caller.write_text(
                "from text_category_profiler.data.df_utils import shared\n",
                encoding="utf-8",
            )
            report = audit(root, ["TCFMain.py"])
            row = next(x for x in report["families"] if x["family"] == "df_utils")
            self.assertEqual(row["versions"][0]["explicit_first_party_import_sources"],
                             ["TCFMain.py"])
            self.assertEqual(row["versions"][1]["explicit_first_party_import_sources"],
                             [])
            self.assertTrue(row["source_bytes_all_identical"])
            self.assertEqual(row["all_versions_ast_identical_definitions"], ["shared"])
            self.assertFalse(row["safe_to_consolidate"])

    def test_corrupt_caller_is_not_ignored(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "bad.py"
            source.write_text("from \n", encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "caller syntax errors"):
                audit(root, ["bad.py"])

    def test_schema_is_json_serializable_without_runtime_evidence(self):
        report = audit(ROOT, [])
        decoded = json.loads(json.dumps(report))
        self.assertFalse(decoded["runtime_verified"])
        self.assertTrue(any("external" in s.lower() for s in decoded["limitations"]))


if __name__ == "__main__":
    unittest.main()
