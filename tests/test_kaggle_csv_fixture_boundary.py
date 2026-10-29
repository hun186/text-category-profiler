"""Guard historical Kaggle CSV sample relocation without running data ingestion."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "experiments" / "fixtures" / "kaggle_csv_sample"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"
OLD_ROOT = ROOT / "text_category_profiler"


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + bytes([0]) + data
    ).hexdigest()


class KaggleCSVFixtureBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.entries = cls.manifest["entries"]

    def test_manifest_is_exactly_original_26_samples(self):
        self.assertEqual(len(self.entries), 26)
        old_names = [item["old_path"] for item in self.entries]
        self.assertEqual(len(set(old_names)), 26)
        self.assertEqual(
            {name.split("/")[1] for name in old_names},
            {"KaggleExtraction", "csvSample"},
        )
        self.assertEqual(
            Counter(name.split("/")[1] for name in old_names),
            {"KaggleExtraction": 2, "csvSample": 24},
        )
        self.assertEqual(
            {p.relative_to(ROOT).as_posix() for p in FIXTURE_ROOT.rglob("*.txt")},
            {item["new_path"] for item in self.entries},
        )

    def test_all_original_git_blobs_and_lengths_unchanged(self):
        for item in self.entries:
            with self.subTest(path=item["new_path"]):
                p = ROOT / item["new_path"]
                self.assertTrue(p.is_file())
                data = p.read_bytes()
                self.assertEqual(len(data), item["size_bytes"])
                self.assertEqual(git_blob_sha(data), item["sha"])

    def test_duplicate_input_copies_and_output_versions_preserved(self):
        inputs = [item for item in self.entries if "/KaggleExtraction/" in item["new_path"]]
        outputs = [item for item in self.entries if "/csvSample/" in item["new_path"]]
        self.assertEqual(len(inputs), 2)
        self.assertEqual(len(set(item["sha"] for item in inputs)), 1)
        self.assertEqual(len(outputs), 24)
        self.assertEqual(
            sorted(Counter(item["sha"] for item in outputs).values()),
            [6, 6, 6, 6],
        )

    def test_old_application_package_sample_paths_are_gone(self):
        for directory in ("KaggleExtraction", "csvSample"):
            with self.subTest(directory=directory):
                self.assertFalse((OLD_ROOT / directory).exists())

    def test_repository_scripts_have_no_literal_moved_csv_sample_paths(self):
        forbidden = (
            "KaggleExtraction/csvSample.txt",
            "KaggleExtraction" + chr(92) + "csvSample.txt",
            "csvSample/123_",
            "csvSample" + chr(92) + "123_",
        )
        source_suffixes = {".py", ".bat", ".ps1", ".sh"}
        violations = []
        for p in ROOT.rglob("*"):
            if not p.is_file() or p.suffix not in source_suffixes:
                continue
            relative = p.relative_to(ROOT).as_posix()
            if relative == "tests/test_kaggle_csv_fixture_boundary.py":
                continue
            if "/TRV_deploy/" in "/" + relative or relative.startswith("vendor/"):
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if any(name in text for name in forbidden):
                violations.append(relative)
        self.assertEqual(violations, [], "Update script references to migrated sample paths")

    def test_manual_kaggle_csv_example_uses_repo_relative_fixture(self):
        source = (ROOT / "text_category_profiler/pipeline/DataConverter_utils.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Path(__file__).resolve().parents[2]", source)
        self.assertIn('"kaggle_csv_sample"', source)
        self.assertIn('"KaggleExtraction" / "csvSample.txt"', source)
        self.assertIn("ROOTPATH = os.path.dirname(FN)", source)
        self.assertNotIn(
            "TopicClassification" + chr(92) + "text_category_profiler" + chr(92) + "KaggleExtraction",
            source,
        )

    def test_other_manual_kaggle_json_example_is_not_relocated(self):
        source = (ROOT / "text_category_profiler/data/df_utils.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('FN = "KaggleExtraction/us/ads.json"', source)
        self.assertFalse(
            (FIXTURE_ROOT / "KaggleExtraction/us/ads.json").exists()
        )


if __name__ == "__main__":
    unittest.main()
