"""BL-001 original Git blob and nonexecuting documentation callsite checks.

Pure stdlib tests; no filesystem writes, FTP access or model imports.
"""
import ast
import hashlib
import unittest

from scripts.bl001_research_caller_audit import ROOT, collect, load_catalog


OLD = ROOT / "text_category_profiler/FTPTEST/abc.txt"
NEW = ROOT / "experiments/fixtures/legacy_ftp_marker/abc.txt"
SNAPSHOT = ROOT / (
    "BertScript/TRV_deploy/deploy-dash-with-gcp-master/"
    "TRV/PythonModule/utils/FTPTEST/abc.txt"
)
BLOB_SHA = "f2ba8f84ab5c1bce84a7b441cb1959cfc7093b7f"


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


class FtpMarkerBoundaryTests(unittest.TestCase):
    def test_old_path_absent_and_new_bytes_unchanged(self):
        self.assertFalse(OLD.exists())
        data = NEW.read_bytes()
        self.assertEqual(len(data), 3)
        self.assertEqual(git_blob_sha(data), BLOB_SHA)

    def test_independent_legacy_snapshot_is_untouched(self):
        self.assertEqual(git_blob_sha(SNAPSHOT.read_bytes()), BLOB_SHA)
        self.assertEqual(NEW.read_bytes(), SNAPSHOT.read_bytes())

    def test_manifest_preserves_original_and_current_paths(self):
        paths = load_catalog(ROOT)
        self.assertEqual(len(paths), 39)
        record = next(x for x in paths if x["original_path"] ==
                      "text_category_profiler/FTPTEST/abc.txt")
        self.assertEqual(
            record["current_path"], "experiments/fixtures/legacy_ftp_marker/abc.txt"
        )

    def test_dataconverter_abc_literal_is_only_standalone_example(self):
        source_file = ROOT / "DatasetConverter/DataConverter.py"
        source = source_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_file))
        matches = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "abc.txt" in node.value
        ]
        examples = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and "rowlist sample:" in node.value.value
            and "abc.txt" in node.value.value
        ]
        self.assertEqual(len(matches), 1, "Reevaluate new literal references")
        self.assertEqual(len(examples), 1, "Reference must remain nonexecuting")

    def test_audit_only_finds_documented_example(self):
        result = collect(ROOT)
        self.assertFalse(result["parse_errors"])
        matches = [
            item for item in result["candidate_matches"]
            if item["basename"] == "abc.txt"
        ]
        self.assertEqual(len(matches), 1, "Recheck any new callers")
        self.assertEqual(matches[0]["source"], "DatasetConverter/DataConverter.py")
        self.assertEqual(matches[0]["evidence"], "ast_string_literal")
        self.assertTrue(any("external" in text for text in result["limitations"]))

    def test_readme_maintains_caller_and_provenance_caveats(self):
        readme = (NEW.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("historical deployment", readme)
        self.assertIn("external", readme)
        self.assertIn("provenance", readme)


if __name__ == "__main__":
    unittest.main()
