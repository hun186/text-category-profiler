"""Dependency-free adapters for source-specific sample records."""

from collections.abc import Iterable, Mapping
from typing import Any


def adapt_czj_sample_records(
    records: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Remove the persisted DataFrame index from CZJ sample rows.

    The legacy pandas adapter required an ``index`` column and returned fresh
    record dictionaries without it. Keep that failure contract explicit while
    making the record transformation independently testable.
    """

    adapted: list[dict[str, Any]] = []
    for row_index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise TypeError(f"CZJ sample row at index {row_index} must be a mapping")
        if "index" not in record:
            raise ValueError(
                f"CZJ sample row at index {row_index} is missing persisted index column"
            )
        adapted.append({key: value for key, value in record.items() if key != "index"})
    return tuple(adapted)
