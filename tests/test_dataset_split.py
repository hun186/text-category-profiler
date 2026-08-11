import unittest

try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None

from DatasetConverter.dataset_split import augment_training_rows
from DatasetConverter.dataset_split import build_split_plan
from DatasetConverter.dataset_split import DatasetSplitPlan
from DatasetConverter.dataset_split import deduplicate_dataset_rows
from DatasetConverter.dataset_split import ensure_train_covers_labels
from DatasetConverter.dataset_split import expand_train_to_cover_labels
from DatasetConverter.dataset_split import iter_dataset_splits
from DatasetConverter.dataset_split import iter_split_bounds
from DatasetConverter.sample_schema import columns_for_sample_rows


class DatasetSplitPlanTests(unittest.TestCase):
    def test_empty_sample_rows_keep_downstream_schema(self):
        self.assertEqual(
            columns_for_sample_rows([]),
            ["file", "InLabel", "OutLabel", "text", "PartNO"],
        )

    def test_reader_rows_define_their_own_columns(self):
        self.assertEqual(columns_for_sample_rows([{"OutLabel": "Scrap"}]), [])

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

    def test_tiny_dataset_expands_train_to_include_each_valid_label(self):
        ratio_plan = build_split_plan(2, train_ratio=0.7, test_ratio=0.1)

        plan = expand_train_to_cover_labels(
            ratio_plan, row_count=2, label_count=2
        )

        self.assertEqual((plan.train, plan.validation, plan.test), (2, 0, 0))

    def test_train_expansion_preserves_test_when_validation_is_sufficient(self):
        ratio_plan = DatasetSplitPlan(train=3, validation=2, test=1)

        plan = expand_train_to_cover_labels(
            ratio_plan, row_count=6, label_count=4
        )

        self.assertEqual((plan.train, plan.validation, plan.test), (4, 1, 1))


@unittest.skipIf(pd is None, "pandas is not installed")
class DatasetDataFrameSplitTests(unittest.TestCase):
    def test_only_training_split_is_augmented_after_deduplication(self):
        dataframe = pd.DataFrame(
            {
                "row_id": [0, 1, 2, 3, 4, 5, 6],
                "OutLabel": ["A", "A", "A", "B", "B", "C", "A"],
                "text": ["a0", "a1", "a2", "b0", "b1", "c0", "a0"],
                "file": [f"source-{index}" for index in range(7)],
            }
        )
        dataframe = deduplicate_dataset_rows(dataframe)
        plan = build_split_plan(len(dataframe), train_ratio=0.5, test_ratio=1 / 6)
        splits = dict(iter_dataset_splits(dataframe, plan))
        validation_before = splits["validation"].copy()
        test_before = splits["test"].copy()

        augmented_train, augmented_count = augment_training_rows(
            splits["train"], samples_per_label=5, text_augmenter=str.upper
        )

        self.assertEqual(augmented_count, 2)
        self.assertEqual(len(augmented_train), 5)
        self.assertEqual(augmented_train["OutLabel"].value_counts().to_dict(), {"A": 5})
        self.assertEqual(augmented_train.iloc[-1]["file"], "source-1")
        pd.testing.assert_frame_equal(splits["validation"], validation_before)
        pd.testing.assert_frame_equal(splits["test"], test_before)

    def test_augmentation_balances_each_training_label_independently(self):
        training = pd.DataFrame(
            {
                "OutLabel": ["A", "A", "B"],
                "text": ["a0", "a1", "b0"],
            }
        )

        augmented, augmented_count = augment_training_rows(
            training, samples_per_label=3, text_augmenter=lambda text: text
        )

        self.assertEqual(augmented_count, 3)
        self.assertEqual(augmented["OutLabel"].value_counts().to_dict(), {"A": 3, "B": 3})

    def test_duplicates_are_removed_before_split_assignment(self):
        dataframe = pd.DataFrame(
            {
                "row_id": [0, 1, 2, 3, 4],
                "OutLabel": ["A", "B", "A", "C", "B"],
                "text": ["same", "dev", "same", "test", "dev"],
            }
        )

        deduplicated = deduplicate_dataset_rows(dataframe)
        plan = build_split_plan(len(deduplicated), train_ratio=1 / 3, test_ratio=1 / 3)
        splits = dict(iter_dataset_splits(deduplicated, plan))

        self.assertEqual(deduplicated["row_id"].tolist(), [0, 1, 3])
        assigned_examples = [
            (row.OutLabel, row.text)
            for split in splits.values()
            for row in split.itertuples()
        ]
        self.assertEqual(len(assigned_examples), len(set(assigned_examples)))

    def test_deduplication_requires_classifier_columns(self):
        with self.assertRaisesRegex(ValueError, "missing columns: OutLabel, text"):
            deduplicate_dataset_rows(pd.DataFrame({"row_id": [1]}))

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
