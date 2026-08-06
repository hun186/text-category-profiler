import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class CombineTestResultModelTypeTests(unittest.TestCase):
    def test_result_combiner_uses_shared_pytorch_model_types(self):
        path = REPOSITORY_ROOT / "BertScript/CombineTestResult.py"
        module = ast.parse(path.read_text(encoding="utf-8"))

        imported_names = {
            alias.name
            for node in module.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "utils.TCF_utils"
            for alias in node.names
        }
        pytorch_branches = [
            node
            for node in ast.walk(module)
            if isinstance(node, ast.Compare)
            and any(
                isinstance(comparator, ast.Name)
                and comparator.id == "PYTORCH_MODEL_TYPES"
                for comparator in node.comparators
            )
        ]

        self.assertIn("PYTORCH_MODEL_TYPES", imported_names)
        self.assertTrue(pytorch_branches)

    def test_shared_pytorch_types_include_mmbert(self):
        path = REPOSITORY_ROOT / "PythonModule/utils/TCF_utils.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        assignments = {
            target.id: ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.Assign)
            for target in node.targets
            if isinstance(target, ast.Name)
            and target.id == "PYTORCH_MODEL_TYPES"
        }

        self.assertIn("PytorchMMBERT", assignments["PYTORCH_MODEL_TYPES"])


if __name__ == "__main__":
    unittest.main()
