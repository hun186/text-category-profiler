"""BL-001 complete tracked-package structural ownership coverage.

The ownership manifest classifies locations, not runtime/call graph or
cross-stage usage; known legacy facades remain preserved separately.
"""
from pathlib import Path
import unittest
from unittest import mock

from scripts.bl001_package_census import (
    ROOT, audit_package, load_ownership, tracked_package_files,
    verify_catalogs,
)


class BL001PackageCensusTests(unittest.TestCase):
    def test_canonical_ownership_has_explicit_valid_domain_and_kind(self):
        entries = load_ownership(ROOT)
        self.assertGreater(len(entries), 0)
        self.assertEqual(len(entries), len({e["path"] for e in entries}))
        self.assertTrue(all(e["path"].startswith("text_category_profiler/") for e in entries))
        self.assertEqual(
            {"domain_module", "domain_document", "package_initializer"},
            {e["kind"] for e in entries},
        )

    def test_every_tracked_package_path_is_accounted_for_without_extras(self):
        report = audit_package(ROOT)
        self.assertEqual(report["unclassified_paths"], [])
        self.assertEqual(report["catalogue_paths_missing"], [])
        self.assertEqual(report["invalid_catalog_entries"], [])
        self.assertEqual(report["identity_failures"], [])
        self.assertEqual(report["summary"]["total_tracked_package_files"], 74)
        self.assertEqual(report["summary"]["legacy_preserved"], 13)
        self.assertEqual(report["summary"]["canonical_domain_owned"], 61)
        self.assertEqual(
            report["summary"]["total_tracked_package_files"],
            report["summary"]["legacy_preserved"]
            + report["summary"]["canonical_domain_owned"],
        )

    def test_new_shared_tsv_writer_is_explicitly_owned_by_data_domain(self):
        report = audit_package(ROOT)
        owner = next(
            x for x in report["files"]
            if x["path"] == "text_category_profiler/data/stage_tsv.py"
        )
        self.assertEqual(owner["ownership"], "canonical")
        self.assertEqual(owner["domain"], "data")
        self.assertEqual(owner["classification"], "domain_module")

    def test_xlsx_writer_is_explicitly_data_domain_owned(self):
        report = audit_package(ROOT)
        candidate = next(
            row for row in report["files"]
            if row["path"] == "text_category_profiler/data/stage_xlsx.py"
        )
        self.assertEqual(candidate["classification"], "domain_module")
        self.assertEqual(candidate["domain"], "data")
        self.assertEqual(candidate["ownership"], "canonical")

    def test_stage_sql_is_canonical_domain_owned(self):
        report = audit_package(ROOT)
        provider = next(
            item for item in report["files"]
            if item["path"] == "text_category_profiler/data/stage_sql.py"
        )
        self.assertEqual(provider["classification"], "domain_module")
        self.assertEqual(provider["domain"], "data")
        self.assertEqual(provider["ownership"], "canonical")

    def test_known_legacy_entrypoints_are_retained_not_mistaken_for_domain_code(self):
        report = audit_package(ROOT)
        legacy = [x for x in report["files"] if x["classification"].startswith("legacy_")]
        self.assertEqual(len(legacy), 13)
        self.assertEqual(
            len([x for x in legacy if x["classification"] == "legacy_compat_entrypoint"]),
            8,
        )
        self.assertTrue(all(x["sha"] and x["size_bytes"] >= 0 for x in legacy))

    def test_domain_docs_are_not_ignored_as_non_python(self):
        report = audit_package(ROOT)
        docs = [e for e in report["files"] if e["classification"] == "domain_document"]
        self.assertEqual({x["path"] for x in docs}, {
            "text_category_profiler/cli/README.md",
            "text_category_profiler/integrations/ES_JOB_TEMPLATE.md",
            "text_category_profiler/visualization/TULIP_BOUNDARY.md",
        })

    def test_catalog_validation_rejects_unknown_untracked_candidate(self):
        tracked = tracked_package_files(ROOT)
        fake = "text_category_profiler/UnreviewedSource.py"
        with self.assertRaisesRegex(AssertionError, "not classified"):
            verify_catalogs(tracked | {fake}, ROOT)

    def test_validation_does_not_need_import_or_optional_services(self):
        with mock.patch("socket.socket", side_effect=AssertionError("no network")):
            data = audit_package(ROOT)
        self.assertIn("structural", " ".join(data["limitations"]).lower())
        self.assertFalse(data["full_runtime_verified"])
        self.assertFalse(data["external_callers_verified"])


if __name__ == "__main__":
    unittest.main()
