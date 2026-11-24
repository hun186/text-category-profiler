"""BL-001: Stage 4 restores DataTable parsed filter state without UI imports."""
import ast
import json
from pathlib import Path
import unittest
from unittest import mock

from BertScript import visualization_callback_state as state
from BertScript import visualization_stage as stage


ROOT = Path(__file__).resolve().parents[1]


class DerivedFilterRestoreTests(unittest.TestCase):
    def test_nonempty_filter_remount_recovers_prior_parsed_expression(self):
        parsed = {"type": "relational-operator", "subType": "contains"}
        raw = json.dumps(parsed)
        previous, effective = state.restore_derived_query_state(
            "{Text} contains 'AI'", None, raw, loads=json.loads,
        )
        self.assertEqual((previous, effective), (parsed, parsed))
        self.assertIs(previous, effective)

    def test_explicit_current_parsed_expression_takes_priority(self):
        previous = {"value": "old"}
        supplied = {"value": "new"}
        old, effective = state.restore_derived_query_state(
            "{Text} contains 'AI'", supplied, json.dumps(previous),
            loads=json.loads,
        )
        self.assertEqual(old, previous)
        self.assertIs(effective, supplied)

    def test_empty_query_does_not_restore_previous_expression(self):
        previous = {"value": "old"}
        old, effective = state.restore_derived_query_state(
            "", None, json.dumps(previous), loads=json.loads,
        )
        self.assertEqual(old, previous)
        self.assertIsNone(effective)

    def test_unparseable_previous_json_propagates_before_any_other_action(self):
        for broken in ("{bad json", None, ""):
            with self.subTest(broken=broken):
                with self.assertRaises((ValueError, TypeError)):
                    state.restore_derived_query_state(
                        "valid", {"current": "ignored"}, broken,
                        loads=json.loads,
                    )

    def test_deserializer_is_called_even_when_restore_is_not_needed(self):
        parser = mock.Mock(return_value={"previous": "parsed"})
        current = {"current": "already parsed"}
        previous, chosen = state.restore_derived_query_state(
            "", current, "source", loads=parser,
        )
        parser.assert_called_once_with("source")
        self.assertIs(chosen, current)
        self.assertEqual(previous, {"previous": "parsed"})

    def test_stage_reexports_exact_same_function_object(self):
        self.assertIs(stage.restore_derived_query_state,
                      state.restore_derived_query_state)
        owner = ROOT / "BertScript/visualization_callback_state.py"
        syntax = ast.parse(owner.read_text(encoding="utf-8-sig"))
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom))
                             for n in ast.walk(syntax)))

    def test_real_callback_uses_restoration_before_side_effects(self):
        gui = ast.parse((ROOT / "BertScript/Test_result_Vis.py").read_text(
            encoding="utf-8-sig"
        ))
        callback = next(n for n in gui.body
                        if isinstance(n, ast.FunctionDef)
                        and n.name == "FilteredDF_update")
        calls = [
            node for node in ast.walk(callback)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "restore_derived_query_state"
        ]
        self.assertEqual(len(calls), 1)
        side_effect_names = {"section", "dfFromSQLite3", "dfOutputer"}
        effects = [
            node for node in ast.walk(callback)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in side_effect_names
        ]
        self.assertTrue(effects)
        self.assertLess(calls[0].lineno, min(n.lineno for n in effects))


if __name__ == "__main__":
    unittest.main()
