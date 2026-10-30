"""Byte-exact baseline for the 27 relocated similarity research artifacts.

All checks are filesystem metadata and byte identity only; no spreadsheet
calculation, text classification, external service or research job is executed.
"""
import ast
import hashlib
import io
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "experiments" / "fixtures" / "bl001_similarity_experiment_inventory.json"
GROUPS = {
    "difflib_without_digits_assimilation",
    "jaro_similarity_with_digits_assimilation",
    "jaro_similarity_without_digits_assimilation",
    "test Document",
}


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


class SimilarityExperimentInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.entries = cls.manifest["entries"]
        cls.root = ROOT / cls.manifest["root"]

    def test_manifest_scope_and_original_paths(self):
        self.assertEqual(self.manifest["schema_version"], 3)
        self.assertEqual(len(self.entries), 27)
        self.assertEqual(sum("relocated_path" in item for item in self.entries), 27)
        self.assertTrue(all("relocated_path" in item for item in self.entries))
        self.assertEqual(len({entry["path"] for entry in self.entries}), 27)
        self.assertEqual(sum(item["size_bytes"] for item in self.entries), 824594)
        self.assertEqual(
            self.manifest["external_callers"],
            "unverified; 15 TXT inputs and 12 XLSX outputs relocated with original blobs; computed/manual/external callers not established",
        )
        for item in self.entries:
            with self.subTest(path=item["path"]):
                self.assertTrue(item["path"].startswith(self.manifest["root"] + "/"))
                self.assertIn(item["group"], GROUPS)
                self.assertIn(item["format"], {"txt", "xlsx"})
                self.assertTrue((ROOT / item.get("relocated_path", item["path"])).is_file())

    def test_complete_directory_file_set_is_preserved(self):
        actual = {
            item.relative_to(ROOT).as_posix()
            for item in self.root.rglob("*") if item.is_file()
        }
        self.assertEqual(actual, set(), "No historical similarity research texts inside application package")
        archive = ROOT / "experiments/fixtures/similarity_experiment_outputs"
        archived = {
            path.relative_to(ROOT).as_posix()
            for path in archive.rglob("*")
            if path.is_file() and path.name != "README.md"
        }
        self.assertEqual(
            archived,
            {item["relocated_path"] for item in self.entries if item["format"] == "xlsx"},
        )
        self.assertEqual(len(archived), 12)
        self.assertTrue((archive / "README.md").is_file())
        input_root = ROOT / "experiments/fixtures/similarity_experiment_inputs"
        actual_txt = {
            path.relative_to(ROOT).as_posix()
            for path in input_root.rglob("*")
            if path.is_file() and path.name != "README.md"
        }
        self.assertEqual(
            actual_txt,
            {item["relocated_path"] for item in self.entries if item["format"] == "txt"},
        )
        self.assertEqual(len(actual_txt), 15)
        self.assertTrue((input_root / "README.md").is_file())
        for item in self.entries:
            with self.subTest(old_path=item["path"]):
                self.assertFalse((ROOT / item["path"]).exists())

    def test_every_historical_git_blob_preserved(self):
        for item in self.entries:
            with self.subTest(path=item["path"]):
                data = (ROOT / item.get("relocated_path", item["path"])).read_bytes()
                self.assertEqual(len(data), item["size_bytes"])
                self.assertEqual(git_blob_sha(data), item["sha"])

    def test_expected_experiment_groups_and_formats(self):
        groups = {group: [] for group in GROUPS}
        for item in self.entries:
            groups[item["group"]].append(item)
        for group in GROUPS - {"test Document"}:
            with self.subTest(group=group):
                self.assertEqual(len(groups[group]), 4)
                self.assertEqual({x["format"] for x in groups[group]}, {"xlsx"})
        self.assertEqual(len(groups["test Document"]), 15)
        self.assertEqual({x["format"] for x in groups["test Document"]}, {"txt"})
        workbook_names = [
            {Path(item["path"]).name for item in groups[group]}
            for group in sorted(GROUPS - {"test Document"})
        ]
        self.assertTrue(all(names == workbook_names[0] for names in workbook_names))


    def test_historical_manual_reader_uses_relocated_path_without_model(self):
        source_file = ROOT / "text_category_profiler/text/similarity_utils.py"
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        original = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == "InnerCrossSimilarityForTextListTest"
        )
        assignments = [
            n for n in original.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "testFNList" for t in n.targets)
        ]
        self.assertEqual(len(assignments), 1)
        for item in (x for x in self.entries if x["format"] == "txt"):
            with self.subTest(path=item["path"]):
                name = Path(item["path"]).name
                assignments[0].value = ast.List(elts=[ast.Constant(name)], ctx=ast.Load())
                isolated = ast.fix_missing_locations(
                    ast.Module(body=[original], type_ignores=[])
                )
                namespace = {"__file__": str(source_file)}
                exec(compile(isolated, str(source_file), "exec"), namespace)
                opened, saved = [], []

                def fake_open(path, mode="rt", encoding=None):
                    self.assertEqual(Path(path), ROOT / item["relocated_path"])
                    self.assertEqual(mode, "rt")
                    self.assertEqual(encoding, "utf-8")
                    opened.append(Path(path))
                    return io.StringIO("bounded sample text")

                def fake_similarity(left, right, saveFN):
                    self.assertEqual(left, right)
                    self.assertEqual(Path(saveFN).parent, Path("."))
                    self.assertEqual(saveFN, name.rpartition(".")[0] + ".xlsx")
                    saved.append(saveFN)

                namespace["open"] = fake_open
                namespace["wrap"] = lambda value, length: [value]
                namespace["InnerCrossSimilarityForTextList"] = fake_similarity
                namespace["InnerCrossSimilarityForTextListTest"]()
                self.assertEqual(len(opened), 1)
                self.assertEqual(len(saved), 1)

    def test_xlsx_files_keep_zip_container_signatures(self):
        for item in self.entries:
            if item["format"] == "xlsx":
                with self.subTest(path=item["path"]):
                    with (ROOT / item["relocated_path"]).open("rb") as handle:
                        self.assertEqual(handle.read(4), b"PK\x03\x04")

    def test_inventory_does_not_claim_all_callers_are_known(self):
        self.assertIn("Not an exhaustive caller audit", self.manifest["purpose"])
        self.assertEqual(self.manifest["external_callers"], "unverified; 15 TXT inputs and 12 XLSX outputs relocated with original blobs; computed/manual/external callers not established")


if __name__ == "__main__":
    unittest.main()
