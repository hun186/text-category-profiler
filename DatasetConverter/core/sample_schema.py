"""Schema contracts for rows handed from sample readers to dataset generation."""

from collections.abc import Mapping, Sequence
from typing import Any


SAMPLE_ROW_COLUMNS = ("file", "InLabel", "OutLabel", "text", "PartNO")
REQUIRED_SAMPLE_ROW_COLUMNS = ("file", "InLabel", "OutLabel", "text")


def validate_sample_rows(
    rows: Sequence[Any], *, source_stage: str
) -> tuple[Mapping[str, Any], ...]:
    """Validate reader rows before DataFrame or artifact side effects.

    ``PartNO`` remains optional because external source adapters historically
    omit it and the DataFrame adapter fills it with zero.
    """

    validated: list[Mapping[str, Any]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError(
                f"{source_stage} row at index {row_index} must be a mapping"
            )

        missing = [column for column in REQUIRED_SAMPLE_ROW_COLUMNS if column not in row]
        if missing:
            raise ValueError(
                f"{source_stage} row at index {row_index} is missing required "
                f"columns: {', '.join(missing)}"
            )
        validated.append(row)

    return tuple(validated)


def columns_for_sample_rows(rows: Sequence[Any]) -> list[str]:
    """Supply the standard schema only when no reader rows define it for us."""

    return list(SAMPLE_ROW_COLUMNS) if not rows else []


SOURCE_METADATA_COLUMNS = ("SrcType", "Src")


def preserve_empty_source_metadata_schema(frame):
    """Keep provenance columns on zero-row regular-source handoffs.

    The nonempty DataConverter path calls GetDataSRC to populate these fields.
    When no regular samples were found, that call is deliberately skipped; the
    empty canonical total table still needs its real Src column because its
    writer requests a Src_Index. Never invent rows or silently drop the index.
    The Series on the existing empty file column preserves index and object
    dtype without importing pandas in this dependency-free policy module.
    """
    if len(frame) == 0:
        for name in SOURCE_METADATA_COLUMNS:
            if name not in frame.columns:
                frame[name] = frame["file"].astype("object")
    return frame
