"""BL-001: mission selection computation has an isolated Stage 4 owner."""
import ast
from pathlib import Path
import unittest

from BertScript.visualization_mission_selection import mission_colortable_rows


ROOT = Path(__file__).resolve().parents[1]


class Stage4MissionSelectionBoundaryTests(unittest.TestCase):
    def test_source_module_is_free_of_dash_and_runtime_apis(self):
        path = ROOT / "BertScript/visualization_mission_selection.py"
        syntax = ast.parse(path.read_text(encoding="utf-8"))
        imports = {
            alias.name for node in ast.walk(syntax)
            if isinstance(node, ast.Import) for alias in node.names
        }
        self.assertEqual(imports, {"ast"})
        self.assertFalse(any(
            isinstance(node, ast.ImportFrom) for node in ast.walk(syntax)
        ))

    def test_none_and_empty_rows_select_nothing(self):
        missions = [{"Topics": "['A']"}]
        colors = [{"Label": "A"}]
        self.assertEqual(mission_colortable_rows(None, missions, colors), [])
        self.assertEqual(mission_colortable_rows([], missions, colors), [])

    def test_unsorted_and_duplicate_topics_keep_original_row_order(self):
        mission_data = [
            {"Topics": "['B', 'A', 'B']"},
            {"Topics": "['A', 'C']"},
        ]
        colors = [
            {"Label": "C"}, {"Label": "A"}, {"Label": "B"},
            {"Label": "A"},
        ]
        # Sorted labels: A, A, B, B, C; each A appears in two color rows.
        self.assertEqual(
            mission_colortable_rows([0, 1], mission_data, colors),
            [1, 3, 1, 3, 2, 2, 0],
        )

    def test_selection_uses_visible_row_indices_and_exact_case(self):
        missions = [
            {"Topics": "['Other']"},
            {"Topics": "['a', 'A']"},
        ]
        colors = [{"Label": "A"}, {"Label": "a"}]
        self.assertEqual(mission_colortable_rows([1], missions, colors), [0, 1])
        self.assertEqual(mission_colortable_rows([0], missions, colors), [])

    def test_invalid_or_nonliteral_topics_raise_without_eval(self):
        for bad in (
            "not valid",
            "__import__('os').system('echo should-not-run')",
            "['A'",
        ):
            with self.subTest(value=bad), self.assertRaises((ValueError, SyntaxError)):
                mission_colortable_rows(
                    [0], [{"Topics": bad}], [{"Label": "A"}],
                )
        with self.assertRaises(IndexError):
            mission_colortable_rows(
                [1], [{"Topics": "['A']"}], [{"Label": "A"}],
            )

    def test_dash_callback_retains_public_name_and_logging(self):
        source = (ROOT / "BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8-sig"
        )
        tree = ast.parse(source)
        callback = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name == "MissionTableSelection"
        )
        self.assertTrue(callback.decorator_list)
        callback.decorator_list = []
        calls = []
        env = {
            "mission_colortable_rows": mission_colortable_rows,
            "key_values": lambda *args, **kwargs: calls.append((args, kwargs)),
        }
        exec(compile(ast.Module(body=[callback], type_ignores=[]),
                     "<stage4-mission-callback>", "exec"), env)
        result = env["MissionTableSelection"](
            [0], [{"Topics": "['A']"}], [{"Label": "A"}],
        )
        self.assertEqual(result, [0])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][0], "Mission selection")

    def test_dash_callback_imports_owner_not_duplicate_logic(self):
        path = ROOT / "BertScript/Test_result_Vis.py"
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        self.assertTrue(any(
            isinstance(node, ast.ImportFrom)
            and node.module == "BertScript.visualization_mission_selection"
            and any(a.name == "mission_colortable_rows" for a in node.names)
            for node in tree.body
        ))
        callback = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef)
            and n.name == "MissionTableSelection"
        )
        self.assertFalse(any(
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "literal_eval"
            for n in ast.walk(callback)
        ))


if __name__ == "__main__":
    unittest.main()
