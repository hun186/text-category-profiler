import unittest

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None

from DatasetConverter.dataset_split import build_split_plan
from DatasetConverter.dataset_split import ensure_train_covers_labels
from DatasetConverter.dataset_split import iter_dataset_splits
from DatasetConverter.dataset_split import iter_split_bounds


class DatasetSplitPlanTests(unittest.TestCase):
    def test_plan_assigns_every_row(self):
        plan = build_split_plan(11, train_ratio=0.6, test_ratio=0.2)

        self.assertEqual((plan.train, plan.validation, plan.test), (6, 3, 2))

    def test_invalid_ratios_are_rejected(self):
        with self.assertRaises(ValueError):
            build_split_plan(10, train_ratio=0.8, test_ratio=0.3)

    def test_split_bounds_are_half_open_and_non_overlapping(self):
        plan = build_split_plan(11, train_ratio=0.6, test_ratio=0.2)

        self.assertEqual(
            list(iter_split_bounds(plan, row_count=11)),
            [("train", 0, 6), ("validation", 6, 9), ("test", 9, 11)],
        )


@unittest.skipIf(pd is None, "pandas is not installed")
class DatasetDataFrameSplitTests(unittest.TestCase):
    def test_splits_are_non_overlapping_and_cover_every_row(self):
        dataframe = pd.DataFrame({"row_id": range(11)})
        plan = build_split_plan(11, train_ratio=0.6, test_ratio=0.2)

        splits = dict(iter_dataset_splits(dataframe, plan))

        self.assertEqual(splits["train"]["row_id"].tolist(), list(range(6)))
        self.assertEqual(splits["validation"]["row_id"].tolist(), [6, 7, 8])
        self.assertEqual(splits["test"]["row_id"].tolist(), [9, 10])
        combined = pd.concat(splits.values(), ignore_index=True)
        self.assertEqual(combined["row_id"].tolist(), list(range(11)))

    def test_train_is_reordered_to_cover_each_label(self):
        dataframe = pd.DataFrame(
            {
                "row_id": [0, 1, 2, 3, 4],
                "OutLabel": ["A", "A", "A", "B", "C"],
            },
            index=[10, 20, 30, 40, 50],
        )

        reordered = ensure_train_covers_labels(dataframe, train_size=3)

        self.assertEqual(set(reordered.iloc[:3]["OutLabel"]), {"A", "B", "C"})
        self.assertEqual(sorted(reordered["row_id"].tolist()), list(range(5)))

if __name__ == "__main__":
    unittest.main()
