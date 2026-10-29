"""Dependency-light preservation gates for unrelocated BL-001 research samples.

No dataset parsing, service calls, model imports, or file relocation occurs here.
"""
import ast
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "experiments" / "fixtures" / "bl001_residual_inventory.json"
CHEN_BASE = "陈德铭呼吁美方为中国赴美企业提供公平公正商业环境"


def git_blob_sha(data):
    prefix = ("blob %d" % len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(prefix + data).hexdigest()


class ResidualResearchInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(INVENTORY.read_text(encoding="utf-8"))
        cls.entries = cls.manifest["entries"]

    def test_bounded_manifest_has_unique_package_root_paths(self):
        self.assertEqual(self.manifest["schema_version"], 4)
        self.assertEqual(len(self.entries), 12)
        self.assertEqual(len({item["path"] for item in self.entries}), 12)
        self.assertTrue(all(
            item["path"].startswith("text_category_profiler/")
            for item in self.entries
        ))
        self.assertEqual(
            {item["classification"] for item in self.entries},
            {"legacy/unknown", "test/experiment"},
        )
        self.assertEqual(self.manifest["external_callers"], "unverified; original paths retained for unrelocated entries only")
        self.assertEqual(sum("relocated_path" in e for e in self.entries), 8)

    def test_original_paths_and_git_blobs_are_preserved(self):
        for item in self.entries:
            with self.subTest(path=item["path"]):
                old_path = ROOT / item["path"]
                if "relocated_path" in item:
                    self.assertFalse(old_path.exists(), "Relocated source must not reappear")
                    path = ROOT / item["relocated_path"]
                else:
                    path = old_path
                self.assertTrue(path.is_file(), "Preserve each tracked Git blob")
                data = path.read_bytes()
                self.assertEqual(len(data), item["size_bytes"])
                self.assertEqual(git_blob_sha(data), item["sha"])

    def test_punctuation_variant_fixtures_are_not_identical(self):
        path = ROOT / "experiments/fixtures/text_normalization"
        mixed = (path / "testFix.txt").read_bytes()
        plain = (path / "testFix - 複製.txt").read_bytes()
        self.assertNotEqual(mixed, plain)
        self.assertIn("，".encode("utf-8"), mixed)
        self.assertNotIn("，".encode("utf-8"), plain)

    def test_ftp_marker_has_identical_legacy_deployment_snapshot(self):
        source = ROOT / "text_category_profiler/FTPTEST/abc.txt"
        snapshot = ROOT / (
            "BertScript/TRV_deploy/deploy-dash-with-gcp-master/"
            "TRV/PythonModule/utils/FTPTEST/abc.txt"
        )
        self.assertEqual(git_blob_sha(source.read_bytes()), git_blob_sha(snapshot.read_bytes()))

    def test_manual_similarity_caller_resolves_chinese_input_fixtures(self):
        path = ROOT / "text_category_profiler/text/similarity_utils.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        function = next(
            item for item in module.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "InnerCrossSimilarityForTextListTest"
        )
        strings = {
            item.value for item in ast.walk(function)
            if isinstance(item, ast.Constant) and isinstance(item.value, str)
        }
        self.assertIn(CHEN_BASE + ".txt", strings)
        self.assertIn(CHEN_BASE + "_space.txt", strings)
        self.assertIn("chinese_similarity", strings)
        self.assertTrue(any(
            isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == "open"
            and item.args
            and isinstance(item.args[0], ast.Name)
            and item.args[0].id == "inputFN"
            for item in ast.walk(function)
        ), "Manual caller must read resolved fixture inputFN")

    def test_ragtest_reference_in_legacy_example_is_comment_only(self):
        path = ROOT / "text_category_profiler/core/utilities.py"
        references = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if "RAGTest.json" in line
        ]
        self.assertTrue(references)
        self.assertTrue(all(line.startswith("#") for line in references))


if __name__ == "__main__":
    unittest.main()
