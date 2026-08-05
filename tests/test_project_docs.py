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


if __name__ == "__main__":
    unittest.main()
