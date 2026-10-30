"""Focused AST characterization for bounded canonical-module import evidence."""
import unittest
from pathlib import Path

from scripts.bl001_canonical_import_audit import (
    ROOT, LIMITATIONS, audit, canonical_modules, resolve_from,
    scan_source, source_area,
)


class CanonicalImportEvidenceTests(unittest.TestCase):
    def test_canonical_modules_are_inventory_derived_and_exclude_legacy(self):
        targets = canonical_modules(ROOT)
        self.assertEqual(len(targets), 44)
        self.assertIn("text_category_profiler.visualization.tulip_graph_builder", targets)
        self.assertNotIn("text_category_profiler.ArtCluESJobTemplate", targets)
        self.assertNotIn("text_category_profiler.core", targets)

    def test_explicit_absolute_imports_and_from_package_resolve(self):
        src = (
            "import text_category_profiler.core.utilities as u\n"
            "from text_category_profiler.data import DB_utils as db\n"
            "from text_category_profiler.visualization.tulip_graph_builder "
            "import BuildGraph\n"
            "from text_category_profiler.core import model_paths\n"
        )
        q, d, b, u, err = scan_source(
            "DatasetConverter/stage.py", src, canonical_modules(ROOT)
        )
        self.assertIsNone(err)
        self.assertEqual(d, [])
        self.assertEqual(b, [])
        self.assertEqual(u, [])
        self.assertEqual(
            {edge["target_module"] for edge in q},
            {
                "text_category_profiler.core.utilities",
                "text_category_profiler.data.DB_utils",
                "text_category_profiler.visualization.tulip_graph_builder",
                "text_category_profiler.core.model_paths",
            },
        )
        self.assertTrue(all(x["area"] == "dataset_converter_workspace" for x in q))

    def test_relative_imports_inside_package_are_resolved_but_not_cross_stage(self):
        source = "from . import model_paths\nfrom ..data import json_utils\n"
        q, d, b, u, err = scan_source(
            "text_category_profiler/core/progress_utils.py",
            source, canonical_modules(ROOT),
        )
        self.assertIsNone(err)
        self.assertEqual(
            {x["target_module"] for x in q},
            {"text_category_profiler.core.model_paths", "text_category_profiler.data.json_utils"},
        )
        self.assertTrue(all(x["area"] == "package_internal" for x in q))

    def test_dynamic_and_bare_candidates_never_count_as_qualified_edges(self):
        src = (
            "import importlib\n"
            "importlib.import_module('text_category_profiler.core.utilities')\n"
            "from utilities import MKDIR\n"
            "s = 'text_category_profiler.data.DB_utils'\n"
        )
        q, dynamic, bare, _, err = scan_source(
            "BertScript/RunClassfier.py", src, canonical_modules(ROOT)
        )
        self.assertIsNone(err)
        self.assertEqual(q, [])
        self.assertEqual(len(dynamic), 1)
        self.assertEqual(dynamic[0]["target_module"], "text_category_profiler.core.utilities")
        self.assertTrue(any("text_category_profiler.core.utilities" in x["possible_targets"] for x in bare))

    def test_non_python_sources_and_entrypoint_roles_are_not_exaggerated(self):
        self.assertEqual(source_area("TCFMain.py"), "root_composition")
        self.assertEqual(source_area("DatasetConverter/DataConverter.py"), "dataset_converter_workspace")
        self.assertEqual(source_area("BertScript/Test_result_Vis.py"), "bert_stage_workspace")
        self.assertEqual(source_area("scripts/bl001_legacy_root_audit.py"), "maintenance_script")
        self.assertEqual(source_area("text_category_profiler/core/utilities.py"), "package_internal")
        self.assertEqual(source_area("ClassesTree/ClassesTree_utils.py"), "taxonomy_workspace")
        self.assertTrue(any("runtime" in x.lower() for x in LIMITATIONS))

    def test_stage4_live_source_has_explicit_tulip_import_syntax(self):
        report = audit(ROOT, ["BertScript/Test_result_Vis.py"])
        target = "text_category_profiler.visualization.tulip_graph_builder"
        matches = [
            item for item in report["qualified_imports"]
            if item["target_module"] == target
        ]
        self.assertTrue(matches)
        self.assertTrue(all(x["area"] == "bert_stage_workspace" for x in matches))

    def test_db_utils_manual_import_is_observed_without_execution(self):
        report = audit(ROOT, ["text_category_profiler/data/DB_utils.py"])
        target = "text_category_profiler.integrations.es_job_template"
        self.assertTrue(any(x["target_module"] == target for x in report["qualified_imports"]))
        self.assertEqual(report["summary"]["unresolved_bare_imports"], 0)
        self.assertFalse(report["runtime_verified"])

    def test_full_audit_tracks_every_canonical_module_even_without_import(self):
        data = audit(ROOT, ["BertScript/Test_result_Vis.py"])
        self.assertEqual(data["summary"]["canonical_modules"], 44)
        self.assertEqual(len(data["module_evidence"]), 44)
        self.assertEqual(
            sum(x["has_explicit_scoped_qualified_import"] for x in data["module_evidence"])
            + data["summary"]["modules_without_scoped_import_syntax"], 44
        )
        self.assertFalse(data["external_callers_verified"])

    def test_syntax_failure_is_reported_not_swallowed(self):
        q, d, b, u, err = scan_source(
            "TCFMain.py", "from \n", canonical_modules(ROOT)
        )
        self.assertEqual((q, d, b, u), ([], [], [], []))
        self.assertEqual(err, "SyntaxError")


if __name__ == "__main__":
    unittest.main()
