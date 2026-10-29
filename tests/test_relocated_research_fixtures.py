"""Byte-exact boundaries for moved RAG/Similarity research-only sample files.

Does not import runtime modules or connect to model/database services.
"""
import ast
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MOVED = {
    "RAGTest.json": ("4df2b417d2f19720218edc1d52ff9e847a385389", 10156),
    "Similarity.tsv": ("9fe2e4ad6660e64a2f3befd7011735340865b345", 34615),
}
DEST = ROOT / "experiments" / "fixtures" / "research_samples"


def git_blob_sha(data):
    return hashlib.sha1(
        ("blob %d" % len(data)).encode("ascii") + bytes([0]) + data
    ).hexdigest()


class ResearchFixtureBoundaryTests(unittest.TestCase):
    def test_original_git_blobs_preserved_at_new_paths(self):
        for name, (expected_sha, expected_size) in MOVED.items():
            with self.subTest(name=name):
                data = (DEST / name).read_bytes()
                self.assertEqual(len(data), expected_size)
                self.assertEqual(git_blob_sha(data), expected_sha)

    def test_no_old_research_filenames_in_package_root(self):
        for name in MOVED:
            with self.subTest(name=name):
                self.assertFalse((ROOT / "text_category_profiler" / name).exists())

    def test_rag_research_concatenated_json_arrays_shape(self):
        # The committed sample contains TWO consecutive JSON arrays. Do not
        # normalize it or pretend it is one standard json.load() document.
        text = (DEST / "RAGTest.json").read_text(encoding="utf-8")
        decoder = json.JSONDecoder()
        cursor = 0
        groups = []
        while cursor < len(text):
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor == len(text):
                break
            group, next_cursor = decoder.raw_decode(text, cursor)
            self.assertGreater(next_cursor, cursor)
            self.assertIsInstance(group, list)
            groups.append(group)
            cursor = next_cursor
        self.assertEqual([len(group) for group in groups], [9, 5])
        self.assertTrue(all(
            isinstance(item, dict)
            and isinstance(item.get("title"), str)
            and isinstance(item.get("content"), str)
            for group in groups for item in group
        ))

    def test_similarity_tsv_sample_shape(self):
        rows = (DEST / "Similarity.tsv").read_bytes().splitlines()
        self.assertGreater(len(rows), 1)
        self.assertEqual(len(rows[0].split(b"\t")), 4)

    def test_referenced_manual_rag_example_is_comment_only_and_retargeted(self):
        path = ROOT / "text_category_profiler/core/utilities.py"
        matching = [
            line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if "RAGTest.json" in line
        ]
        self.assertTrue(matching)
        self.assertTrue(all(line.startswith("#") for line in matching))
        self.assertTrue(all(
            "experiments/fixtures/research_samples/RAGTest.json" in line
            for line in matching
        ))

    def test_louvain_manual_sample_points_to_relocated_fixture(self):
        # Verify the __main__ sample's expression without importing graph
        # dependencies or executing full Louvain clustering.
        source = ROOT / "text_category_profiler/visualization/Graph_utils.py"
        module = ast.parse(source.read_text(encoding="utf-8"))
        main_guard = next(
            node for node in module.body
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "__name__"
        )
        assignment = next(
            node for node in main_guard.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "SimilarityFile"
                for target in node.targets
            )
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "str"
        )
        expression = ast.unparse(assignment.value.args[0])
        self.assertIn("Path(__file__).resolve().parents[2]", expression)
        self.assertIn("'experiments'", expression)
        self.assertIn("'fixtures'", expression)
        self.assertIn("'research_samples'", expression)
        self.assertIn("'Similarity.tsv'", expression)
        self.assertEqual(
            source.resolve().parents[2]
            / "experiments/fixtures/research_samples/Similarity.tsv",
            DEST / "Similarity.tsv",
        )

    def test_original_similarity_tsv_contains_59_louvain_nodes(self):
        rows = (DEST / "Similarity.tsv").read_text(encoding="utf-8").splitlines()
        nodes = set()
        for row in rows:
            fields = row.split("\t")
            self.assertEqual(len(fields), 4)
            nodes.update(fields[:2])
            self.assertGreaterEqual(float(fields[2]), 0)
        self.assertEqual(len(nodes), 59)

    def test_no_old_direct_literal_paths_in_python_sources(self):
        needles = (
            'file="RAGTest.json"',
            'file=\'RAGTest.json\'',
            '"text_category_profiler/RAGTest.json"',
            '"text_category_profiler/Similarity.tsv"',
            'file="Similarity.tsv"',
            'file=\'Similarity.tsv\'',
            "SimilarityFile = r'Similarity.tsv'",
        )
        offenders = []
        for path in ROOT.rglob("*.py"):
            if path == Path(__file__).resolve() or "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            if any(needle in source for needle in needles):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(offenders, [], "Old literal research path consumer detected")

    def test_migration_readme_covers_identity_and_caller_limits(self):
        doc = (DEST / "README.md").read_text(encoding="utf-8")
        for name, (sha, size) in MOVED.items():
            self.assertIn(name, doc)
            self.assertIn(sha, doc)
            self.assertIn(str(size), doc)
        self.assertIn("not", doc.lower())
        self.assertIn("external", doc.lower())


if __name__ == "__main__":
    unittest.main()
