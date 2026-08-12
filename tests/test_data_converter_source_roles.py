import ast
from pathlib import Path
import unittest


class DataConverterSourceRoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("DatasetConverter/DataConverter.py").read_text(
            encoding="utf-8"
        )
        cls.tree = ast.parse(cls.source)

    def test_fixed_and_elasticsearch_builds_are_labeled(self):
        source_roles = []
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "BuildSamplesDfFromPaths":
                continue
            for keyword in node.keywords:
                if keyword.arg == "sourceRole" and isinstance(keyword.value, ast.Constant):
                    source_roles.append(keyword.value.value)

        self.assertIn("fixed test source", source_roles)
        self.assertIn("Elasticsearch source", source_roles)

    def test_source_specific_summaries_replace_ambiguous_reader_summary(self):
        self.assertIn('f"{sourceRole.title()} reader job inputs"', self.source)
        self.assertIn('f"{sourceRole.title()} conversion result"', self.source)
        self.assertIn('key_values("Regular source split plan"', self.source)
        self.assertIn('("test (excluding FixedTest)", split_plan.test)', self.source)

    def test_source_metadata_uses_pipeline_boundary_without_silent_failure(self):
        function = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "GetDataSRC"
        )
        calls = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]

        self.assertIn("collect_source_metadata", calls)
        self.assertFalse(any(isinstance(node, ast.Try) for node in ast.walk(function)))
