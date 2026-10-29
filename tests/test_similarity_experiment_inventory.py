"""Byte-exact baseline for the 27 in-place similarity research artifacts.

All checks are filesystem metadata and byte identity only; no spreadsheet
calculation, text classification, external service or research job is executed.
"""
import hashlib
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
        self.assertEqual(self.manifest["schema_version"], 1)
        self.assertEqual(len(self.entries), 27)
        self.assertEqual(len({entry["path"] for entry in self.entries}), 27)
        self.assertEqual(sum(item["size_bytes"] for item in self.entries), 824594)
        self.assertEqual(
            self.manifest["external_callers"],
            "unverified; original paths retained",
        )
        for item in self.entries:
            with self.subTest(path=item["path"]):
                self.assertTrue(item["path"].startswith(self.manifest["root"] + "/"))
                self.assertIn(item["group"], GROUPS)
                self.assertIn(item["format"], {"txt", "xlsx"})
                self.assertTrue((ROOT / item["path"]).is_file())

    def test_complete_directory_file_set_is_preserved(self):
        actual = {
            item.relative_to(ROOT).as_posix()
            for item in self.root.rglob("*") if item.is_file()
        }
        expected = {item["path"] for item in self.entries}
        self.assertEqual(actual, expected)

    def test_every_historical_git_blob_preserved(self):
        for item in self.entries:
            with self.subTest(path=item["path"]):
                data = (ROOT / item["path"]).read_bytes()
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

    def test_xlsx_files_keep_zip_container_signatures(self):
        for item in self.entries:
            if item["format"] == "xlsx":
                with self.subTest(path=item["path"]):
                    with (ROOT / item["path"]).open("rb") as handle:
                        self.assertEqual(handle.read(4), b"PK\x03\x04")

    def test_inventory_does_not_claim_all_callers_are_known(self):
        self.assertIn("Not an exhaustive caller audit", self.manifest["purpose"])
        self.assertEqual(self.manifest["external_callers"], "unverified; original paths retained")


if __name__ == "__main__":
    unittest.main()
