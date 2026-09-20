import ast
import contextlib
import io
import sys
import unittest
from pathlib import Path

from text_category_profiler.core.log_display import key_values


class VisualizationCp950PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path = Path("BertScript/Test_result_Vis.py")
        tree = ast.parse(cls.source_path.read_text(encoding="utf-8"))
        builder = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == "VisDatatableDFBuilder"
        )
        run_method = next(
            node for node in builder.body
            if isinstance(node, ast.FunctionDef) and node.name == "run"
        )
        preview_statement = next(
            node for node in ast.walk(run_method)
            if isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and any(
                isinstance(part, ast.Constant) and part.value == "rowslist[:3]"
                for part in ast.walk(node.value)
            )
        )
        cls.preview_module = ast.fix_missing_locations(
            ast.Module(body=[preview_statement], type_ignores=[])
        )

    def render_preview(self, encoding):
        raw_output = io.BytesIO()
        console = io.TextIOWrapper(raw_output, encoding=encoding, errors="strict")
        namespace = {"key_values": key_values, "rowslist": [["华", 42]]}

        original_stdout = sys.stdout
        with contextlib.redirect_stdout(console):
            exec(
                compile(self.preview_module, str(self.source_path), "exec"),
                namespace,
            )
            console.flush()
        self.assertIs(sys.stdout, original_stdout)
        return raw_output.getvalue().decode(encoding)

    def test_rows_preview_is_safe_and_operator_readable_on_cp950(self):
        output = self.render_preview("cp950")

        self.assertIn("rowslist[:3]", output)
        self.assertIn("42", output)
        self.assertIn("?", output)

    def test_rows_preview_preserves_unicode_on_utf8(self):
        output = self.render_preview("utf-8")

        self.assertIn("rowslist[:3]", output)
        self.assertIn("华", output)
        self.assertIn("42", output)


if __name__ == "__main__":
    unittest.main()
