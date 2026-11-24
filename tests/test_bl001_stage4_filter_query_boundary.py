"""Characterization of the dependency-light Stage 4 filter-query boundary."""
import ast
from pathlib import Path
import unittest

from BertScript.visualization_filter import (
    construct_filter, operators, split_filter_part, to_string,
)


ROOT = Path(__file__).resolve().parents[1]


class FakeSeries:
    def __init__(self, column):
        self.column = column

    def astype(self, _type):
        return self

    @property
    def str(self):
        return self

    def contains(self, value):
        return ("contains", self.column, value)

    def startswith(self, value):
        return ("datestartswith", self.column, value)


class FakeDataFrame:
    def __init__(self):
        self.filters = []

    def __getitem__(self, item):
        if isinstance(item, tuple):
            self.filters.append(item)
            return self
        return FakeSeries(item)


def expression(value, subtype="value"):
    return {"type": "expression", "subType": subtype, "value": value}


def comparison(operator, left, right):
    return {
        "type": "relational-operator", "subType": operator,
        "left": left, "right": right,
    }


class Stage4FilterBoundaryTests(unittest.TestCase):
    def test_module_has_no_gui_or_dataframe_runtime_imports(self):
        path = ROOT / "BertScript" / "visualization_filter.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(n, (ast.Import, ast.ImportFrom))
                             for n in ast.walk(tree)))
        self.assertEqual(
            {n.name for n in tree.body if isinstance(n, ast.FunctionDef)},
            {"to_string", "split_filter_part", "construct_filter"},
        )

    def test_stage4_compatibility_exports_are_imported_not_redefined(self):
        path = ROOT / "BertScript" / "Test_result_Vis.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = [
            node for node in tree.body if isinstance(node, ast.ImportFrom)
            and node.module == "BertScript.visualization_filter"
        ]
        self.assertEqual(len(imports), 1)
        self.assertEqual(
            {name.name for name in imports[0].names},
            {"to_string", "split_filter_part", "construct_filter", "operators"},
        )
        definitions = {
            n.name for n in tree.body if isinstance(n, ast.FunctionDef)
        }
        self.assertTrue(definitions.isdisjoint({
            "to_string", "split_filter_part", "construct_filter",
        }))

    def test_to_string_operator_and_literal_contract(self):
        self.assertEqual(to_string({"type": "relational-operator", "subType": "="}), "==")
        self.assertEqual(to_string({"type": "relational-operator", "subType": ">="}), ">=")
        self.assertEqual(to_string({"type": "logical-operator", "subType": "&&"}), "&")
        self.assertEqual(to_string({"type": "logical-operator", "subType": "||"}), "|")
        self.assertEqual(to_string(expression("ABC")), '"ABC"')
        self.assertEqual(to_string(expression(22)), 22)
        self.assertEqual(to_string(expression("text", subtype="field")), "text")

    def test_legacy_split_filter_parses_exact_identifiers_and_values(self):
        examples = (
            ("{InfoScoreMean} ge 10", ("InfoScoreMean", "ge", 10.0)),
            ("{InfoScoreMean} lt 10", ("InfoScoreMean", "lt", 10.0)),
            ("{Label} contains 'AI'", ("Label", "contains", "AI")),
            ("{Date} datestartswith \"2026\"", ("Date", "datestartswith", "2026")),
            ("{Score} >= 12", ("Score", "ge", 12.0)),
        )
        self.assertEqual(operators[0], ["ge ", ">="])
        for raw, expected in examples:
            with self.subTest(raw=raw):
                self.assertEqual(split_filter_part(raw), expected)
        self.assertEqual(split_filter_part("invalid"), [None, None, None])

    def test_none_query_preserves_same_dataframe(self):
        frame = FakeDataFrame()
        self.assertEqual(construct_filter(None, frame), ("", frame))
        self.assertEqual(frame.filters, [])

    def test_simple_relation_and_and_or_queries_preserve_strings(self):
        frame = FakeDataFrame()
        query = comparison(">=", expression("Score", "field"), expression(9))
        self.assertEqual(construct_filter(query, frame), ("Score >= 9", frame))
        combined = {
            "type": "logical-operator", "subType": "&&",
            "left": query,
            "right": comparison("=", expression("Tag", "field"),
                                expression("臺灣")),
        }
        self.assertEqual(
            construct_filter(combined, frame),
            ('Score >= 9 & Tag == "臺灣"', frame),
        )

    def test_contains_and_datestartswith_use_dataframe_column_operations(self):
        for operator, value, mask in (
            ("contains", "AI", ("contains", "Text", "AI")),
            ("datestartswith", 2026, ("datestartswith", "Text", "2026")),
        ):
            with self.subTest(operator=operator):
                frame = FakeDataFrame()
                query = comparison(operator,
                                   expression("Text", "field"),
                                   expression(value))
                self.assertEqual(construct_filter(query, frame), ("", frame))
                self.assertEqual(frame.filters, [mask])


if __name__ == "__main__":
    unittest.main()
