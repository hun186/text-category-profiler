"""Pure transformations between sample readers and dataset assembly."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectedSamples:
    """Rows and multi-label counters returned by a group of reader jobs."""

    rows: tuple[Mapping[str, Any], ...]
    multi_label_counts: tuple[Any, ...]


def collect_reader_results(
    reader_results: Iterable[Sequence[Any]],
) -> CollectedSamples:
    """Assemble reader-job results without DataFrame or filesystem access.

    Each reader job uses the legacy ``(rows, multi_label_count)`` contract.
    Keeping its assembly here makes the read/assemble boundary independently
    testable while leaving source-specific reading in the existing adapters.
    """

    rows: list[Mapping[str, Any]] = []
    multi_label_counts: list[Any] = []
    for result_index, result in enumerate(reader_results):
        if len(result) != 2:
            raise ValueError(
                "reader result at index "
                f"{result_index} must contain rows and a multi-label count"
            )

        result_rows, multi_label_count = result
        if not isinstance(result_rows, (list, tuple)):
            raise TypeError(
                f"reader rows at index {result_index} must be a list or tuple"
            )
        rows.extend(result_rows)
        multi_label_counts.append(multi_label_count)

    return CollectedSamples(tuple(rows), tuple(multi_label_counts))
