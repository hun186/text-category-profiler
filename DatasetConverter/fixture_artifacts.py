"""Standard-library artifact writer for the isolated converter fixture.

This is a narrow contract probe, not a replacement for the pandas/SQLite
production output adapter. It lets the source-to-split handoff run in minimal
development containers before optional runtime dependencies are installed.
"""

import csv
from pathlib import Path
from typing import Iterable

from DatasetConverter.source_collection import TextSource


def write_classifier_tsv(
    path: str | Path, sources: Iterable[TextSource]
) -> Path:
    """Write the classifier's two-column label/text TSV contract."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.writer(output_file, delimiter="\t", lineterminator="\n")
        writer.writerow(("OutLabel", "text"))
        writer.writerows((source.label, source.text) for source in sources)
    return output_path
