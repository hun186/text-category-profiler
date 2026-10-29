"""BL-001 byte-exact Chinese similarity manual research fixtures.

The legacy manual function is run in isolation with a computation stub:
no NLP/model import or workbook write is performed.
"""
import ast
import hashlib
from pathlib import Path
import unittest
import warnings


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "text_category_profiler"
NEW = ROOT / "experiments/fixtures/chinese_similarity"
BASE = "陈德铭呼吁美方为中国赴美企业提供公平公正商业环境"
EXPECTED = {
    BASE + ".txt": ("f7746d15b8f245ec281331ef4e69662dc874b0fb", 2304),
    BASE + "_space.txt": ("bd25bc335ba2cc0f6dd0301dbdccf83c496b2150", 3060),
    BASE + ".xlsx": ("26c6439ca50fc1d21a5909a8a3b18d2802d49e74", 6822),
    BASE + "_space.xlsx": ("cb00157b9ca927f2976a5134b270639fda6fb675", 7124),
}


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + b"\0" + data
    ).hexdigest()


def isolated_manual_function():
    source = ROOT / "text_category_profiler/text/similarity_utils.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    function = next(
        node for node in module.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "InnerCrossSimilarityForTextListTest"
    )
    namespace = {"__file__": str(source)}
    isolated = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(isolated, str(source), "exec"), namespace)
    return namespace["InnerCrossSimilarityForTextListTest"]


class ChineseSimilarityFixtureTests(unittest.TestCase):
    def test_exact_git_blobs_and_original_root_paths_absent(self):
        for name, (sha, size) in EXPECTED.items():
            with self.subTest(name=name):
                self.assertFalse((OLD / name).exists())
                data = (NEW / name).read_bytes()
                self.assertEqual(len(data), size)
                self.assertEqual(git_blob_sha(data), sha)

    def test_historical_outputs_remain_xlsx_zip_containers(self):
        for name in EXPECTED:
            if name.endswith(".xlsx"):
                with self.subTest(name=name):
                    self.assertEqual((NEW / name).read_bytes()[:4], b"PK\x03\x04")

    def test_isolated_manual_caller_reads_new_inputs_and_preserves_output_cwd(self):
        fn = isolated_manual_function()
        namespace = fn.__globals__
        calls = []
        original_open = open
        opened_files = []

        def read_expected_fixture(path, mode="rt", encoding=None):
            source = Path(path)
            self.assertTrue(source.is_absolute())
            self.assertEqual(source.parent, NEW)
            self.assertIn(source.name, [BASE + ".txt", BASE + "_space.txt"])
            handle = original_open(source, mode=mode, encoding=encoding)
            opened_files.append(handle)
            return handle

        def fake_similarity(left, right, saveFN):
            self.assertEqual(left, right)
            self.assertTrue(left)
            self.assertEqual(Path(saveFN).parent, Path("."))
            self.assertFalse(Path(saveFN).is_absolute())
            self.assertIn(saveFN, [BASE + ".xlsx", BASE + "_space.xlsx"])
            calls.append(saveFN)

        namespace["open"] = read_expected_fixture
        namespace["wrap"] = lambda text, n: [
            text[i:i + n] for i in range(0, len(text), n)
        ]
        namespace["InnerCrossSimilarityForTextList"] = fake_similarity
        frozen_before = {
            name: (NEW / name).read_bytes()
            for name in EXPECTED if name.endswith(".xlsx")
        }
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always", ResourceWarning)
            fn()
        self.assertFalse(
            [w for w in notices if issubclass(w.category, ResourceWarning)],
            "Manual caller must not emit unclosed file ResourceWarnings",
        )
        self.assertEqual(len(opened_files), 2)
        self.assertTrue(all(stream.closed for stream in opened_files))
        self.assertEqual(calls, [BASE + ".xlsx", BASE + "_space.xlsx"])
        for name, data in frozen_before.items():
            self.assertEqual((NEW / name).read_bytes(), data)

    def test_readme_discloses_provenance_and_external_callers(self):
        contents = (NEW / "README.md").read_text(encoding="utf-8")
        self.assertIn("working directory", contents)
        self.assertIn("provenance", contents)
        self.assertIn("unverified", contents)


if __name__ == "__main__":
    unittest.main()
