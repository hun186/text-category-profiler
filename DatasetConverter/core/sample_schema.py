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
    """Restore the true sample columns when a zero-row source has none.

    A regular-source result starts with SAMPLE_ROW_COLUMNS, but optional
    FixedTest/Elasticsearch branches can use a bare pandas.DataFrame() with
    zero columns. They still export an *empty* sample table with physical text
    and Src columns because downstream canonical SQLite requests real indexes
    on both names. Do not fabricate any sample row, remove the indexes, or
    mask missing columns on nonempty source data.

    Keep any existing columns and their dtypes, inserting only missing schema
    columns. An empty index-to-Series conversion creates object columns with
    the original DataFrame index and does not import pandas into this module.
    """
    if len(frame) == 0:
        for name in (*SAMPLE_ROW_COLUMNS, *SOURCE_METADATA_COLUMNS):
            if name not in frame.columns:
                frame[name] = frame.index.to_series().astype("object")
    return frame
