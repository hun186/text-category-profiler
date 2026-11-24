"""BL-001: own DataTable callback loop policy outside Stage 4 lifecycle."""
import ast
from pathlib import Path
import unittest

from BertScript import visualization_callback_state as callback_state
from BertScript import visualization_stage as stage


ROOT = Path(__file__).resolve().parents[1]
NAMES = (
    "is_spurious_datatable_filter_notification",
    "datatable_filter_state",
    "is_redundant_table_filter_event",
    "is_redundant_table_page_event",
    "restore_derived_query_state",
)


class Stage4CallbackStateBoundaryTests(unittest.TestCase):
    def test_old_stage_names_are_same_function_objects_as_new_owner(self):
        for name in NAMES:
            with self.subTest(name=name):
                self.assertIs(getattr(stage, name), getattr(callback_state, name))

    def test_pure_owner_has_no_runtime_import_and_stage_does_not_redefine(self):
        owner = ast.parse(
            (ROOT / "BertScript/visualization_callback_state.py").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            for node in ast.walk(owner)
        ))
        stage_tree = ast.parse(
            (ROOT / "BertScript/visualization_stage.py").read_text(
                encoding="utf-8"
            )
        )
        old_definitions = {
            node.name for node in stage_tree.body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertTrue(set(NAMES).isdisjoint(old_definitions))
        imported = [
            node for node in stage_tree.body
            if isinstance(node, ast.ImportFrom)
            and node.module == "BertScript.visualization_callback_state"
        ]
        self.assertEqual(len(imported), 1)
        self.assertEqual(
            {alias.name for alias in imported[0].names}, set(NAMES)
        )

    def test_remount_filter_guard_preserves_true_user_changes(self):
        guard = callback_state.is_spurious_datatable_filter_notification
        remount = [{
            "prop_id": "VisDatatable.derived_filter_query_structure",
            "value": None,
        }]
        base = {
            "filter_query": "", "sort_by": [],
            "derived_query_structure": None,
            "previous_derived_query_structure": None,
        }
        self.assertTrue(guard(remount, **base))
        self.assertFalse(guard(remount, **dict(
            base, filter_query="{InfoScoreMean} ge 10"
        )))
        self.assertFalse(guard(remount, **dict(
            base, sort_by=[{"column_id": "InfoScoreMean", "direction": "asc"}]
        )))
        self.assertFalse(guard(
            remount + [{"prop_id": "KeyWordTable.selected_rows"}],
            **base,
        ))

    def test_filtered_revision_increments_without_changing_previous(self):
        original = {"revision": 6, "filter_query": "original"}
        a = callback_state.datatable_filter_state(
            "{Score} ge 4", [{"column_id": "Score", "direction": "asc"}],
            None, previous=original,
        )
        b = callback_state.datatable_filter_state(
            "{Score} ge 4", [], None, previous=a,
        )
        self.assertEqual(a["revision"], 7)
        self.assertEqual(b["revision"], 8)
        self.assertEqual(original, {"revision": 6, "filter_query": "original"})

    def test_redundancy_applies_only_to_table_property_events(self):
        state = callback_state.datatable_filter_state(
            "{Score} ge 4", [], None,
        )
        kwargs = dict(
            filter_query="{Score} ge 4", sort_by=[],
            derived_query_structure=None, previously_applied=state,
        )
        self.assertTrue(callback_state.is_redundant_table_filter_event(
            [{"prop_id": "VisDatatable.filter_query"}], **kwargs,
        ))
        self.assertFalse(callback_state.is_redundant_table_filter_event(
            [{"prop_id": "KeyWordTable.selected_rows"}], **kwargs,
        ))
        self.assertFalse(callback_state.is_redundant_table_filter_event(
            [{"prop_id": "VisDatatable.sort_by"}],
            **dict(kwargs, sort_by=[{"column_id": "Score", "direction": "desc"}]),
        ))

    def test_page_remount_is_not_a_user_navigation(self):
        event = [{"prop_id": "VisDatatable.page_current", "value": 1}]
        check = callback_state.is_redundant_table_page_event
        self.assertTrue(check(event, page_current=1, last_rendered={
            "page_current": 1,
        }))
        self.assertFalse(check(event, page_current=2, last_rendered={
            "page_current": 1,
        }))
        self.assertFalse(check([], page_current=1, last_rendered={
            "page_current": 1,
        }))


if __name__ == "__main__":
    unittest.main()
