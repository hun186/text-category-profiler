import unittest

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None


@unittest.skipIf(pd is None, "pandas is not installed")
class DictRowsListToDFTests(unittest.TestCase):
    def test_empty_rows_can_define_dataframe_schema(self):
        from text_category_profiler.data.df_utils import DictRowsListToDF

        dataframe = DictRowsListToDF(
            [],
            Cols=["file", "InLabel", "OutLabel", "text", "PartNO"],
        )

        self.assertTrue(dataframe.empty)
        self.assertEqual(
            list(dataframe.columns),
            ["file", "InLabel", "OutLabel", "text", "PartNO"],
        )

    def test_populated_rows_keep_legacy_positional_column_rename(self):
        from text_category_profiler.data.df_utils import DictRowsListToDF

        dataframe = DictRowsListToDF(
            [["Scrap", "sample"]],
            Cols=["OutLabel", "text"],
        )

        self.assertEqual(list(dataframe.columns), ["OutLabel", "text"])
        self.assertEqual(dataframe.iloc[0].to_dict(), {"OutLabel": "Scrap", "text": "sample"})
