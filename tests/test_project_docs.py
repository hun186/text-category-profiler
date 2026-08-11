from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ProjectDocumentationTests(unittest.TestCase):
    def test_root_requirements_exists_with_core_sections(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        for expected in [
            "numpy",
            "pandas",
            "dash",
            "tensorflow>=1.11.0",
            "transformers",
        ]:
            self.assertIn(expected, requirements)

    def test_readme_documents_install_and_lightweight_tests(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("python -m pip install -r requirements.txt", readme)
        self.assertIn("python -m unittest discover -s tests", readme)
        self.assertIn("完整 `python TCFMain.py ...` 流程仍需本機資料", readme)

    def test_readme_presents_scoring_recommendation_methodology(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        asset = ROOT / "docs" / "assets" / "text-scoring-recommendation.svg"

        self.assertIn("docs/assets/text-scoring-recommendation.svg", readme)
        for concept in ["切片策略", "評分治理", "文件彙總", "推薦決策"]:
            self.assertIn(concept, readme)
        self.assertTrue(asset.is_file())

    def test_readme_presents_dataset_optimization_loop(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        asset = ROOT / "docs" / "assets" / "dataset-optimization-loop.svg"

        self.assertIn("docs/assets/dataset-optimization-loop.svg", readme)
        self.assertIn("TextClassificationDatasetOptimization/", readme)
        for concept in ["覆蓋盤點", "即時議題查核", "Taxonomy 治理", "正文資料化", "品質閉環"]:
            self.assertIn(concept, readme)
        self.assertTrue(asset.is_file())

    def test_readme_keeps_core_content_expanded(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertNotIn("<details>", readme)
        self.assertNotIn("<summary>", readme)
        self.assertIn("### 功能特色", readme)


if __name__ == "__main__":
    unittest.main()
