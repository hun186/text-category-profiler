import ast
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from DatasetConverter.dataframe_source import concat_dataframes
from DatasetConverter.dataframe_source import dataframe_from_dict
from DatasetConverter.dataframe_source import empty_dataframe


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class DatasetDataframeSourceTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        calls = self.calls
        fake_pandas = types.ModuleType("pandas")

        class FakeDataFrame:
            @classmethod
            def from_dict(cls, data, **kwargs):
                calls.append(("from_dict", data, kwargs))
                return "from-dict result"

            def __new__(cls):
                calls.append(("empty",))
                return "empty result"

        def fake_concat(frames, **kwargs):
            calls.append(("concat", frames, kwargs))
            return "concat result"

        fake_pandas.DataFrame = FakeDataFrame
        fake_pandas.concat = fake_concat
        self.pandas_patch = patch.dict(sys.modules, {"pandas": fake_pandas})
        self.pandas_patch.start()

    def tearDown(self):
        self.pandas_patch.stop()

    def test_dataframe_from_dict_preserves_constructor_contract(self):
        result = dataframe_from_dict(
            {"A": 1}, orient="index", columns=["count"]
        )
        self.assertEqual(result, "from-dict result")
        self.assertEqual(
            self.calls,
            [
                (
                    "from_dict",
                    {"A": 1},
                    {"orient": "index", "columns": ["count"]},
                )
            ],
        )

    def test_empty_dataframe_preserves_constructor_contract(self):
        self.assertEqual(empty_dataframe(), "empty result")
        self.assertEqual(self.calls, [("empty",)])

    def test_concat_preserves_index_contract(self):
        frames = [object(), object()]
        self.assertEqual(
            concat_dataframes(frames, ignore_index=True), "concat result"
        )
        self.assertEqual(
            self.calls,
            [("concat", frames, {"ignore_index": True})],
        )

    def test_entrypoint_and_adapter_have_no_module_scope_pandas_import(self):
        for relative_path in (
            "DatasetConverter/DataConverter.py",
            "DatasetConverter/dataframe_source.py",
        ):
            tree = ast.parse(
                (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")
            )
            imports = [
                alias.name
                for node in tree.body
                if isinstance(node, ast.Import)
                for alias in node.names
            ]
            from_imports = [
                node.module
                for node in tree.body
                if isinstance(node, ast.ImportFrom)
            ]
            self.assertNotIn("pandas", imports, relative_path)
            self.assertNotIn("pandas.io", from_imports, relative_path)


if __name__ == "__main__":
    unittest.main()
