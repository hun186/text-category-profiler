"""BL-001 labelViewer import/provider contract without Dash or browser startup."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "BertScript" / "pages" / "labelViewer" / "layout_interactivity.py"
PROVIDER = ROOT / "BertScript" / "reusable_components.py"
MAIN_STAGE4 = ROOT / "BertScript" / "Test_result_Vis.py"


def module_ast(path):
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


class LabelViewerProviderTests(unittest.TestCase):
    def test_layout_uses_explicit_stage_provider(self):
        tree = module_ast(VIEW)
        imports = [
            (alias.name, alias.asname)
            for statement in ast.walk(tree) if isinstance(statement, ast.Import)
            for alias in statement.names
        ]
        self.assertIn(("BertScript.reusable_components", "rc"), imports)
        self.assertNotIn(("reusable_components", "rc"), imports)
        # Keep the original call sites and the exported names in sync.
        used = {
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name) and node.value.id == "rc"
        }
        self.assertEqual(used, {"Row", "CustomSlider"})

    def test_main_stage4_uses_explicit_local_provider_with_existing_api(self):
        # The Stage 4 script is also directly executable: importing the bare
        # reusable_components name depends on sys.path and can select a
        # different module from the intended BertScript provider.
        tree = module_ast(MAIN_STAGE4)
        qualified = [
            node for node in tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "BertScript"
            and any(alias.name == "reusable_components" and alias.asname == "rc"
                    for alias in node.names)
        ]
        self.assertEqual(len(qualified), 1)
        self.assertFalse(any(
            isinstance(node, ast.Import)
            and any(alias.name == "reusable_components" for alias in node.names)
            for node in ast.walk(tree)
        ))
        used = {
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name) and node.value.id == "rc"
        }
        self.assertEqual(
            used, {"Row", "Col", "Card", "CardContent", "CustomSlider",
                   "CustomRangeSlider"},
        )
        provider = module_ast(PROVIDER)
        functions = {
            node.name for node in provider.body
            if isinstance(node, ast.FunctionDef)
        }
        assigns = {
            target.id for node in provider.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)
        }
        self.assertTrue(used <= functions | assigns)
        # Check the real provider module identity without starting Dash.
        self.assertEqual(qualified[0].module, "BertScript")

    def test_provider_api_remains_defined_without_importing_dash(self):
        tree = module_ast(PROVIDER)
        names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"build_component", "CustomSlider"} <= names)
        row = [
            n for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "Row" for t in n.targets)
        ]
        self.assertEqual(len(row), 1)
        self.assertIsInstance(row[0].value, ast.Call)

    def test_row_and_slider_keep_legacy_shape_with_stub_dash(self):
        tree = module_ast(PROVIDER)
        definitions = [
            n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name in {"build_component", "CustomSlider"}
        ]
        row = next(
            n for n in tree.body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "Row" for t in n.targets)
        )
        def fake(tag):
            return lambda *args, **kwargs: (tag, args, kwargs)

        scope = {
            "html": SimpleNamespace(Div=fake("Div"), P=fake("P"), Br=fake("Br")),
            "dcc": SimpleNamespace(Slider=fake("Slider")),
        }
        exec(
            compile(ast.Module(body=definitions + [row], type_ignores=[]),
                    str(PROVIDER), "exec"),
            scope,
        )
        component = scope["Row"](["content"], className="extra")
        self.assertEqual(component[0], "Div")
        self.assertEqual(component[2]["className"], "row extra")

        slider = scope["CustomSlider"](id="example", min=1, max=5, label="L")
        self.assertEqual(slider[0], "Div")
        nested = slider[1][0]
        self.assertEqual(nested[2][0], "Slider")
        self.assertEqual(nested[2][2]["value"], 3)
        self.assertEqual(nested[2][2]["marks"], {1: "1", 3: "3", 5: "5"})


if __name__ == "__main__":
    unittest.main()
