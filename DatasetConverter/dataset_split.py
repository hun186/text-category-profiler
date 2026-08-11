"""Pure helpers for planning and slicing classifier datasets.

Keeping these operations separate from ``DataConverter.py`` makes the split
contract testable without importing the converter's model and I/O dependencies.
"""

from dataclasses import dataclass
from typing import Any, Iterator, Tuple


@dataclass(frozen=True)
class DatasetSplitPlan:
    """Number of source rows assigned to each classifier dataset split."""

    train: int
    validation: int
    test: int

    def items(self) -> Tuple[Tuple[str, int], ...]:
        return (
            ("train", self.train),
            ("validation", self.validation),
            ("test", self.test),
        )


def build_split_plan(
    row_count: int, train_ratio: float, test_ratio: float
) -> DatasetSplitPlan:
    """Build the legacy train/dev/test allocation with explicit validation."""

    if row_count < 0:
        raise ValueError("row_count cannot be negative")
    if not 0 <= train_ratio <= 1 or not 0 <= test_ratio <= 1:
        raise ValueError("train and test ratios must be between 0 and 1")
    if train_ratio + test_ratio > 1:
        raise ValueError("train and test ratios cannot add up to more than 1")

    train = int(row_count * train_ratio)
    test = int(row_count * test_ratio)
    return DatasetSplitPlan(
        train=train,
        validation=row_count - train - test,
        test=test,
    )


def ensure_train_covers_labels(
    dataframe: Any, train_size: int, label_column: str = "OutLabel"
) -> Any:
    """Move one row per label to the front when the train split can hold them."""

    if dataframe.empty or train_size <= 0 or label_column not in dataframe.columns:
        return dataframe

    labels = list(dataframe[label_column].dropna().unique())
    if not labels or len(labels) > train_size:
        return dataframe

    train_labels = set(dataframe.iloc[:train_size][label_column].dropna().unique())
    missing_labels = [label for label in labels if label not in train_labels]
    if not missing_labels:
        return dataframe

    column_values = dataframe[label_column].tolist()
    selected_positions = [column_values.index(label) for label in labels]
    selected_position_set = set(selected_positions)
    remaining_positions = [
        position
        for position in range(len(dataframe))
        if position not in selected_position_set
    ]
    return dataframe.iloc[selected_positions + remaining_positions].reset_index(drop=True)


def iter_dataset_splits(
    dataframe: Any, plan: DatasetSplitPlan
) -> Iterator[Tuple[str, Any]]:
    """Yield non-overlapping splits whose combined rows exactly cover the input."""

    for name, start, stop in iter_split_bounds(plan, len(dataframe)):
        yield name, dataframe.iloc[start:stop].copy()


def iter_split_bounds(
    plan: DatasetSplitPlan, row_count: int
) -> Iterator[Tuple[str, int, int]]:
    """Yield half-open positional bounds and verify plan/dataframe agreement."""

    offset = 0
    for name, size in plan.items():
        next_offset = offset + size
        yield name, offset, next_offset
        offset = next_offset
    if offset != row_count:
        raise ValueError(
            f"split plan covers {offset} rows but dataframe contains {row_count}"
        )
