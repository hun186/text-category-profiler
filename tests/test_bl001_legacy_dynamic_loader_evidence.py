"""BL-001 dynamic import callsites are evidence, never runtime proof."""
import json
from pathlib import Path
import unittest
from unittest import mock

from scripts.bl001_legacy_root_audit import (
    ROOT, audit, load_catalog, scan_dynamic_loader_calls,
)


SYNTHETIC = """
import importlib
import runpy
from importlib import import_module

direct = importlib.import_module("text_category_profiler.selector")
also = __import__("text_category_profiler.Edited_zipfile")
bare = import_module("text_category_profiler.utilities_RAND")
script = runpy.run_path("text_category_profiler/ES_ingest_txt_to_es.py")
ignored = importlib.import_module("json")
unknown = importlib.import_module(module_name)
script_dynamic = runpy.run_path(dynamic_path)
from pathlib import Path
irrelevant = Path("text_category_profiler/selector.py")
"""


class LegacyDynamicLoaderEvidenceTests(unittest.TestCase):
    def test_static_literal_known_target_calls_are_classified(self):
        observed = scan_dynamic_loader_calls(
            "candidate.py", SYNTHETIC, load_catalog(ROOT),
        )
        known = [x for x in observed
                 if x["classification"] == "known_legacy_literal"]
        self.assertEqual(
            {x["target"] for x in known},
            {
                "text_category_profiler/selector.py",
                "text_category_profiler/Edited_zipfile.py",
                "text_category_profiler/utilities_RAND.py",
                "text_category_profiler/ES_ingest_txt_to_es.py",
            },
        )
        self.assertTrue(all(
            row["evidence"] == "ast_loader_call_candidate"
            and row["source"] == "candidate.py"
            and isinstance(row["line"], int)
            for row in known
        ))

    def test_computed_arguments_remain_unresolved_without_leaking_source(self):
        observed = scan_dynamic_loader_calls(
            "candidate.py", SYNTHETIC, load_catalog(ROOT),
        )
        unknown = [
            x for x in observed
            if x["classification"] == "computed_or_missing_argument"
        ]
        self.assertEqual(len(unknown), 2)
        self.assertTrue(all(x["target"] is None for x in unknown))
        self.assertNotIn("dynamic_path", str(unknown))
        self.assertNotIn("module_name", str(unknown))

    def test_arbitrary_library_and_path_literals_do_not_infer_legacy_usage(self):
        observed = scan_dynamic_loader_calls(
            "candidate.py", SYNTHETIC, load_catalog(ROOT),
        )
        self.assertFalse(any("json" in str(x) for x in observed))
        self.assertEqual(len(observed), 6)

    def test_ambiguous_plain_function_name_remains_candidate_only(self):
        observed = scan_dynamic_loader_calls(
            "sample.py",
            "def import_module(x):\n    return x\n"
            "name = import_module(some_name)\n",
            load_catalog(ROOT),
        )
        self.assertEqual(len(observed), 1)
        self.assertEqual(observed[0]["classification"],
                         "computed_or_missing_argument")
        self.assertIsNone(observed[0]["target"])

    def test_malformed_file_returns_no_dynamic_evidence(self):
        observed = scan_dynamic_loader_calls("bad.py", "def :\n",
                                             load_catalog(ROOT))
        self.assertEqual(observed, [])

    def test_real_audit_retains_unverified_external_caller_status(self):
        source = ROOT / "text_category_profiler/ES_ingest_txt_to_es.py"
        report = audit(ROOT, [
            str(source.relative_to(ROOT)).replace("\\", "/"),
        ])
        self.assertIn("dynamic_loader_callsites", report)
        self.assertIs(report["external_dynamic_callers_verified"], False)
        self.assertEqual(len(report["preservation"]), 13)
        self.assertTrue(all(x["blob_matches_baseline"]
                            for x in report["preservation"]))
        self.assertFalse(any(x.get("runtime_verified") is True
                             for x in report["dynamic_loader_callsites"]))

    def test_no_dynamic_loader_is_invoked_during_analysis(self):
        with mock.patch("importlib.import_module",
                        side_effect=AssertionError("execution forbidden")):
            result = scan_dynamic_loader_calls(
                "candidate.py", SYNTHETIC, load_catalog(ROOT),
            )
        self.assertEqual(len(result), 6)


if __name__ == "__main__":
    unittest.main()
