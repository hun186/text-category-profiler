"""Pure helpers for planning and slicing classifier datasets.

Keeping these operations separate from ``DataConverter.py`` makes the split
contract testable without importing the converter's model and I/O dependencies.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Sequence, Tuple


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


def deduplicate_dataset_rows(
    dataframe: Any, columns: Sequence[str] = ("OutLabel", "text")
) -> Any:
    """Remove duplicate classifier examples before assigning dataset splits.

    Deduplicating each split independently can leave the same example in both
    training and evaluation data.  Performing the operation once, before the
    split plan is calculated, prevents that leakage and avoids repeating the
    same work for every split.
    """

    if dataframe.empty:
        return dataframe.reset_index(drop=True)

    missing_columns = [column for column in columns if column not in dataframe.columns]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"cannot deduplicate dataset; missing columns: {missing}")

    return dataframe.drop_duplicates(subset=list(columns)).reset_index(drop=True)


def augment_training_rows(
    dataframe: Any,
    samples_per_label: int,
    text_augmenter: Callable[[str], str],
    label_column: str = "OutLabel",
    text_column: str = "text",
) -> Tuple[Any, int]:
    """Expand minority labels in a training split to the requested row count.

    This helper intentionally operates on an already-created training split so
    augmented variants cannot be assigned to validation or test data.  Original
    row metadata is retained for traceability; only the sample text is changed.
    """

    if samples_per_label <= 0 or dataframe.empty:
        return dataframe, 0

    missing_columns = [
        column
        for column in (label_column, text_column)
        if column not in dataframe.columns
    ]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"cannot augment training dataset; missing columns: {missing}")

    augmented_rows = []
    for label in dataframe[label_column].dropna().unique():
        label_rows = dataframe[dataframe[label_column] == label]
        source_rows = list(label_rows.to_dict(orient="records"))
        for sequence in range(len(source_rows), samples_per_label):
            source_row = source_rows[sequence % len(source_rows)].copy()
            source_text = str(source_row[text_column])
            source_row[text_column] = f"{sequence}_{text_augmenter(source_text)}"
            augmented_rows.append(source_row)

    if not augmented_rows:
        return dataframe, 0

    import pandas as pd

    augmented_frame = pd.DataFrame.from_records(
        augmented_rows, columns=dataframe.columns
    )
    combined = pd.concat([dataframe, augmented_frame], ignore_index=True)
    return combined, len(augmented_rows)


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


def expand_train_to_cover_labels(
    plan: DatasetSplitPlan, row_count: int, label_count: int
) -> DatasetSplitPlan:
    """Move evaluation capacity to train when each label needs a training row.

    A positional reorder cannot cover every label when the ratio-derived train
    size is smaller than the number of labels. This occurs especially with tiny
    smoke datasets: two valid labels at a 70% ratio previously produced one
    training row and one validation row, which the classifier correctly rejected
    as single-class training. Prefer retaining test rows, then consume validation
    and test capacity only as needed to make label coverage possible.
    """

    if row_count < 0 or label_count < 0:
        raise ValueError("row_count and label_count cannot be negative")
    if sum(size for _, size in plan.items()) != row_count:
        raise ValueError("split plan and row_count do not agree")

    required_train_size = min(row_count, label_count)
    shortfall = max(0, required_train_size - plan.train)
    if shortfall == 0:
        return plan

    from_validation = min(shortfall, plan.validation)
    remaining_shortfall = shortfall - from_validation
    from_test = min(remaining_shortfall, plan.test)
    return DatasetSplitPlan(
        train=plan.train + from_validation + from_test,
        validation=plan.validation - from_validation,
        test=plan.test - from_test,
    )


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
