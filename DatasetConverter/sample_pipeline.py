"""Pure transformations between sample readers and dataset assembly."""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CollectedSamples:
    """Rows and multi-label counters returned by a group of reader jobs."""

    rows: tuple[Mapping[str, Any], ...]
    multi_label_counts: tuple[Any, ...]


@dataclass(frozen=True)
class SourceMetadata:
    """Source columns resolved from a sample's provenance path."""

    source_type: Any
    source: Any


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


def aggregate_multi_label_counts(
    multi_label_counts: Iterable[Any],
) -> dict[tuple[Any, ...], int]:
    """Aggregate reader multi-label counters without stage or logger state.

    Reader adapters use ``None`` when a sample has no multi-label metadata.
    Label sets are sorted before becoming dictionary keys so equivalent sets
    from different workers are combined deterministically.
    """

    aggregated: dict[tuple[Any, ...], int] = {}
    for result_index, result in enumerate(multi_label_counts):
        if result is None:
            continue
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError(
                "multi-label count result at index "
                f"{result_index} must contain labels and a count"
            )

        labels, count = result
        if labels is None:
            continue
        key = tuple(sorted(labels))
        aggregated[key] = aggregated.get(key, 0) + count
    return aggregated


def collect_source_metadata(
    file_paths: Iterable[str],
    *,
    labels: Sequence[str],
    resolver: Callable[[str, Sequence[str]], Sequence[Any]],
) -> tuple[SourceMetadata, ...]:
    """Resolve provenance columns before the DataFrame adapter mutates data.

    The injected resolver preserves the legacy path policy while this function
    owns result validation and row-level diagnostics. A path that does not map
    to known metadata remains the legacy ``(None, None)`` result.
    """

    resolved: list[SourceMetadata] = []
    for row_index, file_path in enumerate(file_paths):
        result = resolver(file_path, labels)
        if not isinstance(result, (list, tuple)) or len(result) != 2:
            raise ValueError(
                f"source metadata result at row {row_index} for path "
                f"{file_path!r} must contain source type and source"
            )
        source_type, source = result
        resolved.append(SourceMetadata(source_type, source))
    return tuple(resolved)
