"""Schema contract for rows handed from sample readers to dataset generation."""

from typing import Any, Sequence


SAMPLE_ROW_COLUMNS = ("file", "InLabel", "OutLabel", "text", "PartNO")


def columns_for_sample_rows(rows: Sequence[Any]) -> list[str]:
    """Supply the standard schema only when no reader rows define it for us."""

    return list(SAMPLE_ROW_COLUMNS) if not rows else []
