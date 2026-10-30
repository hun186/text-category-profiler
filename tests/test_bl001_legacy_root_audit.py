"""Regression for bounded residual package-root catalog and caller audit."""
import ast
from pathlib import Path
import unittest

from scripts.bl001_legacy_root_audit import (
    ROOT, MANIFEST, audit, blob_sha, load_catalog, scan_source, source_in_scope,
    target_module,
)


class LegacyRootAuditTests(unittest.TestCase):
    def test_catalog_covers_all_direct_root_files_and_nested_legacy_entries(self):
        items = load_catalog(ROOT)
        self.assertEqual(len(items), 13)
        root_files = {
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "text_category_profiler").iterdir()
            if path.is_file()
        }
        self.assertEqual(
            root_files,
            {x["path"] for x in items if x["path"].count("/") == 1},
        )
        self.assertEqual(len([x for x in items if x["category"] == "compat_entrypoint"]), 8)
        self.assertTrue(all(x["external_callers"] == "unverified" for x in items))

    def test_stable_blobs_paths_and_canonical_targets(self):
        for item in load_catalog(ROOT):
            with self.subTest(path=item["path"]):
                actual = (ROOT / item["path"]).read_bytes()
                self.assertEqual(len(actual), item["size_bytes"])
                self.assertEqual(blob_sha(actual), item["sha"])
                self.assertTrue((ROOT / item["canonical_path"]).is_file())

    def test_old_vendor_assets_preserved_without_claiming_readme_byte_identity(self):
        base = ROOT / "text_category_profiler/dijkstra_algorithm_master"
        vendor = ROOT / "vendor/dijkstra_algorithm_master"
        for name in ("LICENSE", "simple_graph.txt", "seattle_area.txt"):
            with self.subTest(file=name):
                self.assertEqual((base / name).read_bytes(), (vendor / name).read_bytes())
        self.assertNotEqual((base / "README.md").read_bytes(),
                            (vendor / "README.md").read_bytes())

    def test_scanner_detects_direct_and_from_imports_with_aliases(self):
        catalog = load_catalog(ROOT)
        source = (
            "import text_category_profiler.selector as old_selector\n"
            "from text_category_profiler import ArtCluESJobTemplate as art\n"
            "from ArtCluESJobTemplate import esJobTemplate\n"
            "import Edited_zipfile as zip_patch\n"
            "from text_category_profiler.tulip_utils.Graph_Builder import BuildGraph\n"
            "from text_category_profiler.dijkstra_algorithm_master "
            "import dijkstra_algorithm as dj\n"
            "# text_category_profiler/selector.py old path\n"
            "x = 'text_category_profiler.utilities_RAND'\n"
        )
        imports, hints, bare, error = scan_source("sample.py", source, catalog)
        self.assertIsNone(error)
        self.assertEqual(
            {x["module"] for x in imports},
            {
                "text_category_profiler.selector",
                "text_category_profiler.ArtCluESJobTemplate",
                "text_category_profiler.tulip_utils.Graph_Builder",
                "text_category_profiler.dijkstra_algorithm_master.dijkstra_algorithm",
            },
        )
        self.assertEqual(
            {x["name"] for x in bare},
            {"ArtCluESJobTemplate", "Edited_zipfile"},
        )
        self.assertTrue(all(
            x["evidence"] == "unresolved_bare_import"
            and len(x["candidate_targets"]) >= 1
            for x in bare
        ))
        self.assertTrue(any(x["evidence"] == "text_or_comment" for x in hints))
        self.assertTrue(any(x["evidence"] == "ast_string_literal" for x in hints))

    def test_out_of_scope_paths_and_parse_errors_are_explicit(self):
        for path in ("tests/test_a.py", "vendor/module.py",
                     "BertScript/TRV_deploy/demo.py",
                     "SomeTree/tests/test_b.py", "experiments/script.py"):
            self.assertFalse(source_in_scope(path))
        self.assertTrue(source_in_scope("BertScript/Test_result_Vis.py"))
        self.assertEqual(
            target_module("text_category_profiler/tulip_utils/Graph_Builder.py"),
            "text_category_profiler.tulip_utils.Graph_Builder",
        )
        _, _, _, error = scan_source("broken.py", "if :\n", load_catalog(ROOT))
        self.assertEqual(error, "SyntaxError")

    def test_real_manual_db_utils_uses_canonical_template_no_bare_candidate(self):
        source = ROOT / "text_category_profiler/data/DB_utils.py"
        parsed = ast.parse(source.read_text(encoding="utf-8"))
        imports = [
            node for node in ast.walk(parsed)
            if isinstance(node, ast.ImportFrom)
            and node.module == "text_category_profiler.integrations.es_job_template"
        ]
        self.assertEqual(len(imports), 1)
        self.assertEqual([alias.name for alias in imports[0].names], ["esJobTemplate"])
        data = audit(ROOT, ["text_category_profiler/data/DB_utils.py"])
        self.assertEqual(data["unresolved_bare_import_candidates"], [])
        self.assertEqual(data["parse_errors"], [])

    def test_stage4_uses_canonical_tulip_visualization_module(self):
        file = ROOT / "BertScript/Test_result_Vis.py"
        tree = ast.parse(file.read_text(encoding="utf-8"))
        imports = {
            alias.name
            for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
            and node.module == "text_category_profiler.visualization.tulip_graph_builder"
            for alias in node.names
        }
        self.assertEqual(imports, {"BuildGraph", "ClusterMetaNodeGraph"})

    def test_audit_is_read_only_and_does_not_claim_external_proof(self):
        data = audit(ROOT, ["BertScript/Test_result_Vis.py"])
        self.assertTrue(data["root_files_match_catalog"])
        self.assertEqual(data["catalogued_residual_entries"], 13)
        self.assertEqual(data["tracked_python_files_scanned"], 1)
        self.assertEqual(data["parse_errors"], [])
        self.assertTrue(all(
            p["blob_matches_baseline"] and p["size_matches_baseline"]
            and p["canonical_exists"] for p in data["preservation"]
        ))
        self.assertIn("external", " ".join(data["limitations"]).lower())


if __name__ == "__main__":
    unittest.main()
