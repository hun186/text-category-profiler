"""Stage 4 pagination decisions run without Dash or pandas imports."""
import ast
from pathlib import Path
import unittest

from BertScript.visualization_pagination import select_table_page


ROOT = Path(__file__).resolve().parents[1]


class Stage4PaginationBoundaryTests(unittest.TestCase):
    def test_filter_shrinking_pages_clamps_old_page_number(self):
        for length, size, requested, expected in (
            (0, 10, 99, 0),
            (1, 10, 99, 0),
            (10, 10, 99, 0),
            (11, 10, 99, 1),
            (20, 10, 99, 1),
            (21, 10, 99, 2),
            (11, 10, -2, 0),
            (21, 10, None, 0),
            (21, 10, 2, 2),
            (21, 10, 1, 1),
        ):
            with self.subTest(rows=length, size=size, page=requested):
                self.assertEqual(
                    select_table_page(length, size, requested, "other"), expected
                )

    def test_page_size_change_resets_even_when_old_page_still_exists(self):
        self.assertEqual(
            select_table_page(100, 10, 3, "Page Size Bar"), 0
        )
        self.assertEqual(
            select_table_page(100, 10, 3, "VisDatatable"), 3
        )
        self.assertEqual(
            select_table_page(0, 10, 3, "Page Size Bar"), 0
        )

    def test_invalid_page_size_preserves_error_signaling(self):
        with self.assertRaises(ZeroDivisionError):
            select_table_page(20, 0, 3, "other")
        with self.assertRaises(TypeError):
            select_table_page(20, None, 3, "other")

    def test_page_state_module_does_not_import_gui_or_services(self):
        source = ROOT / "BertScript/visualization_pagination.py"
        syntax = ast.parse(source.read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom))
                             for n in ast.walk(syntax)))
        self.assertEqual(
            {node.name for node in syntax.body
             if isinstance(node, ast.FunctionDef)},
            {"select_table_page"},
        )

    def test_table_update_calls_page_policy_once_before_building_table(self):
        source = ROOT / "BertScript/Test_result_Vis.py"
        syntax = ast.parse(source.read_text(encoding="utf-8-sig"))
        imported = [
            node for node in syntax.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "BertScript.visualization_pagination"
        ]
        self.assertEqual(len(imported), 1)
        self.assertEqual(
            [alias.name for alias in imported[0].names],
            ["select_table_page"],
        )
        callback = next(
            node for node in syntax.body if isinstance(node, ast.FunctionDef)
            and node.name == "table_update"
        )
        calls = [
            node for node in ast.walk(callback)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"select_table_page", "Build_VisDatatable"}
        ]
        self.assertEqual(
            len([node for node in calls
                 if node.func.id == "select_table_page"]), 1
        )
        self.assertLess(
            next(node.lineno for node in calls
                 if node.func.id == "select_table_page"),
            next(node.lineno for node in calls
                 if node.func.id == "Build_VisDatatable"),
        )

    def test_callback_still_publishes_page_state_and_one_based_label(self):
        source = (ROOT / "BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8"
        )
        table = source[source.index("def table_update("):
                       source.index("def func1(")]
        self.assertIn('{"page_current": page_current}', table)
        self.assertIn("page_current + 1,", table)
        self.assertIn("page_current=page_current, page_size=page_size,", table)
        self.assertNotIn('if button_id in ["Page Size Bar"]:', table)


if __name__ == "__main__":
    unittest.main()
