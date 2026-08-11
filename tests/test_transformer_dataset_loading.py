import ast
import io
import math
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TRANSFORMER_SCRIPT = REPOSITORY_ROOT / "BertScript/TextClassification_transformers.py"


def _load_functions(*function_names):
    tree = ast.parse(
        TRANSFORMER_SCRIPT.read_text(encoding="utf-8"),
        filename=str(TRANSFORMER_SCRIPT),
    )
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in function_names
    ]
    namespace = {"math": math}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(TRANSFORMER_SCRIPT), "exec"), namespace)
    return namespace


class TransformerDatasetLoadingTests(unittest.TestCase):
    def setUp(self):
        self.namespace = _load_functions(
            "LoadSamples", "validation_runtime_config"
        )

    def test_optional_missing_validation_dataset_returns_no_samples(self):
        for count_result in ([], [0]):
            with self.subTest(count_result=count_result):
                self.namespace["sqlite3Query"] = (
                    lambda *args, **kwargs: count_result
                )

                with redirect_stdout(io.StringIO()):
                    samples = self.namespace["LoadSamples"](
                        "missing-dev.sql3", label2id={"A": 0}, allow_empty=True
                    )

                self.assertEqual(samples, [])

    def test_missing_training_dataset_remains_fatal(self):
        self.namespace["sqlite3Query"] = lambda *args, **kwargs: []

        with redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "Required dataset is missing or empty"):
                self.namespace["LoadSamples"](
                    "missing-train.sql3", label2id={"A": 0}
                )

    def test_empty_validation_disables_trainer_evaluation(self):
        has_validation, strategy = self.namespace["validation_runtime_config"]([])

        self.assertFalse(has_validation)
        self.assertEqual(strategy, "no")

    def test_nonempty_validation_keeps_step_evaluation(self):
        has_validation, strategy = self.namespace["validation_runtime_config"](
            [{"labels": 0}]
        )

        self.assertTrue(has_validation)
        self.assertEqual(strategy, "steps")


if __name__ == "__main__":
    unittest.main()
